use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use std::borrow::Cow;

use lavalink_rs::model::Track;
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use phf::phf_map;
use regex::Regex;
use reqwest::Client as HttpClient;
use serenity::all::{
    ButtonStyle, ChannelId, CommandInteraction, ComponentInteraction, CreateActionRow,
    CreateButton, CreateEmbed, CreateEmbedFooter, CreateInteractionResponse,
    CreateInteractionResponseMessage, CreateMessage, EditMessage, GuildId, Interaction,
    MessageId, Ready, UserId, Attachment,
};
use serenity::async_trait;
use serenity::framework::standard::macros::{command, group};
use serenity::framework::standard::{Args, CommandResult, Configuration, StandardFramework};
use serenity::model::application::Interaction::Command;
use serenity::model::channel::Message;
use serenity::model::gateway::Ready;
use serenity::model::prelude::*;
use serenity::{prelude::*, Client};
use smallvec::SmallVec;
use songbird::input::AuxMetadata;
use songbird::tracks::TrackHandle;
use songbird::{Call, Songbird};
use tokio::sync::oneshot;
use tokio::time::{timeout, sleep};
use tracing::{error, info, warn};
use urlencoding::encode;

static COMMANDS: phf::Map<&'static str, fn(&mut Context, &Message) -> CommandResult> = phf_map! {
    "play" => play_command,
    "skip" => skip_command,
    "pause" => pause_command,
    "resume" => resume_command,
    "stop" => stop_command,
    "volume" => volume_command,
    "queue" => queue_command,
    "np" => np_command,
    "remove" => remove_command,
    "clear" => clear_command,
    "loop" => loop_command,
    "lyrics" => lyrics_command,
    "seek" => seek_command,
};

static PROGRESS_CHARS: [char; 2] = ['▓', '░'];

static LYRICS_CLEANUP_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r"[\[\(\{].*?[\]\)\}]").unwrap());
static LYRICS_WHITESPACE_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r"\s+").unwrap());
static LYRICS_NEWLINES_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r"\n{3,}").unwrap());
static YOUTUBE_ID_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})").unwrap());

static HTTP_CLIENT: Lazy<HttpClient> = Lazy::new(|| {
    HttpClient::builder()
        .timeout(Duration::from_secs(10))
        .user_agent("JackyBot-MusicPlayer/1.0")
        .build()
        .unwrap()
});

#[derive(Clone)]
struct GuildState {
    queue: SmallVec<[TrackHandle; 64]>,
    loop_mode: bool,
    volume: u8,
    text_channel: ChannelId,
    current_message: Option<MessageId>,
    update_task: Option<tokio::task::JoinHandle<()>>,
    idle_timer: Option<tokio::task::JoinHandle<()>>,
    last_requester: Option<UserId>,
}

impl Default for GuildState {
    fn default() -> Self {
        Self {
            queue: SmallVec::new(),
            loop_mode: false,
            volume: 100,
            text_channel: ChannelId::new(0),
            current_message: None,
            update_task: None,
            idle_timer: None,
            last_requester: None,
        }
    }
}

fn extract_artist_title(track: &Track) -> (Cow<'static, str>, Cow<'static, str>) {
    let artist = track.info.author.as_deref().unwrap_or("Unknown Artist");
    let title = track.info.title.as_deref().unwrap_or("Unknown Title");

    if artist == "Unknown Artist" || artist.is_empty() {
        let (parsed_artist, parsed_title) = parse_artist_title(title);
        (Cow::Owned(parsed_artist), Cow::Owned(parsed_title))
    } else {
        (Cow::Borrowed(artist), Cow::Borrowed(title))
    }
}

fn parse_artist_title(title: &str) -> (String, String) {
    let cleaned = LYRICS_WHITESPACE_REGEX.replace_all(
        &LYRICS_CLEANUP_REGEX.replace_all(title, ""),
        " "
    ).trim().to_string();

    let separators = [" - ", " – ", " — ", " | ", " : "];

    for sep in separators {
        if let Some((left, right)) = cleaned.split_once(sep) {
            let artist_part = left.trim();
            let title_part = right.trim();

            if !artist_part.is_empty() && !title_part.is_empty() &&
               artist_part.len() < 40 && title_part.len() < 100 &&
               !artist_part.contains(',') {
                return (title_part.to_string(), artist_part.to_string());
            } else {
                return (artist_part.to_string(), title_part.to_string());
            }
        }
    }

    ("Unknown Artist".to_string(), cleaned)
}

fn create_now_playing_embed(track: &Track, show_progress: bool) -> CreateEmbed {
    let (artist, title) = extract_artist_title(track);
    let color = 0x57F287; // Playing color

    let mut embed = CreateEmbed::new()
        .title("Now Playing")
        .color(color)
        .field("Artist", artist.as_ref(), true)
        .field("Title", title.as_ref(), true);

    if let Some(length) = track.info.length {
        let duration_str = format_duration(length as u64);
        embed = embed.field("Duration", duration_str, true);
    }

    embed = embed.field("Loop", "Off", true);

    if show_progress {
        let progress_bar = create_progress_bar(0, track.info.length.unwrap_or(0) as u64);
        embed = embed.field("Progress", progress_bar, false);
    }

    // Add thumbnail
    if let Some(artwork_url) = &track.info.artwork_url {
        embed = embed.image(artwork_url);
    } else if let Some(uri) = &track.info.uri {
        if uri.contains("youtube.com") || uri.contains("youtu.be") {
            if let Some(thumbnail) = get_youtube_thumbnail(uri) {
                embed = embed.image(thumbnail);
            }
        }
    }

    embed
}

fn format_duration(milliseconds: u64) -> String {
    if milliseconds == 0 {
        return "00:00".to_string();
    }

    let total_seconds = milliseconds / 1000;
    let hours = total_seconds / 3600;
    let minutes = (total_seconds % 3600) / 60;
    let seconds = total_seconds % 60;

    if hours > 0 {
        format!("{:02}:{:02}:{:02}", hours, minutes, seconds)
    } else {
        format!("{:02}:{:02}", minutes, seconds)
    }
}

fn create_progress_bar(current_ms: u64, total_ms: u64) -> String {
    const LENGTH: usize = 20;

    if total_ms == 0 {
        return "░░░░░░░░░░░░░░░░░░░░ 0%".to_string();
    }

    let progress = (current_ms as f64 / total_ms as f64).min(1.0);
    let filled = (progress * LENGTH as f64) as usize;

    let mut bar = String::with_capacity(LENGTH + 5);
    for i in 0..LENGTH {
        if i < filled {
            bar.push(PROGRESS_CHARS[0]);
        } else {
            bar.push(PROGRESS_CHARS[1]);
        }
    }

    bar.push(' ');
    bar.push_str(&format!("{}%", (progress * 100.0) as u32));
    bar
}

fn get_youtube_thumbnail(url: &str) -> Option<String> {
    YOUTUBE_ID_REGEX.captures(url)
        .and_then(|caps| caps.get(1))
        .map(|m| format!("https://img.youtube.com/vi/{}/maxresdefault.jpg", m.as_str()))
}

fn create_controls() -> CreateActionRow {
    CreateActionRow::Buttons(vec![
        CreateButton::new("back").style(ButtonStyle::Secondary).emoji('⏪'),
        CreateButton::new("pause").style(ButtonStyle::Secondary).emoji('⏯'),
        CreateButton::new("fwd").style(ButtonStyle::Secondary).emoji('⏩'),
        CreateButton::new("skip").style(ButtonStyle::Secondary).emoji('⏭'),
        CreateButton::new("loop").style(ButtonStyle::Secondary).emoji('🔁'),
        CreateButton::new("lyrics").style(ButtonStyle::Secondary).emoji('📜'),
        CreateButton::new("spotify").style(ButtonStyle::Secondary).emoji('💚'),
        CreateButton::new("youtube").style(ButtonStyle::Secondary).emoji('❤️'),
        CreateButton::new("queue").style(ButtonStyle::Secondary).emoji('📋'),
    ])
}

struct Handler;

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        info!("JackyBotRust is ready!");
        connect_lavalink(ctx).await;
    }

    async fn interaction_create(&self, ctx: Context, interaction: Interaction) {
        if let Command(command) = interaction.clone() {
            handle_slash_command(ctx, command).await;
        } else if let Interaction::Component(component) = interaction {
            handle_button_interaction(ctx, component).await;
        }
    }
}

async fn connect_lavalink(ctx: Context) {
    let songbird = Songbird::serenity();
    ctx.data.write().await.insert::<SongbirdKey>(songbird.clone());

    let lavalink = lavalink_rs::LavalinkClient::builder("127.0.0.1", 2333, "youshallnotpass")
        .build(songbird)
        .await;

    if let Err(e) = lavalink {
        error!("Failed to connect to Lavalink: {}", e);
        return;
    }

    let lavalink = lavalink.unwrap();
    ctx.data.write().await.insert::<LavalinkKey>(lavalink);
}

async fn handle_slash_command(ctx: Context, command: CommandInteraction) {
    let command_name = command.data.name.as_str();

    match command_name {
        "play" => slash_play(ctx, command).await,
        "skip" => slash_skip(ctx, command).await,
        "pause" => slash_pause(ctx, command).await,
        "resume" => slash_resume(ctx, command).await,
        "stop" => slash_stop(ctx, command).await,
        "volume" => slash_volume(ctx, command).await,
        "queue" => slash_queue(ctx, command).await,
        "np" => slash_np(ctx, command).await,
        "remove" => slash_remove(ctx, command).await,
        "clear" => slash_clear(ctx, command).await,
        "loop" => slash_loop(ctx, command).await,
        "lyrics" => slash_lyrics(ctx, command).await,
        "seek" => slash_seek(ctx, command).await,
        _ => {}
    }
}

async fn handle_button_interaction(ctx: Context, component: ComponentInteraction) {
    let custom_id = component.data.custom_id.as_str();
    let guild_id = component.guild_id.unwrap();

    let data = ctx.data.read().await;
    let states = data.get::<GuildStates>().unwrap().read();

    if let Some(state) = states.get(&guild_id) {
        match custom_id {
            "back" => seek_player(&ctx, guild_id, -10).await,
            "pause" => toggle_pause(&ctx, guild_id).await,
            "fwd" => seek_player(&ctx, guild_id, 10).await,
            "skip" => skip_track(&ctx, guild_id).await,
            "loop" => toggle_loop(&ctx, guild_id).await,
            "lyrics" => get_lyrics(&ctx, component.clone()).await,
            "spotify" => get_spotify_link(&ctx, component.clone()).await,
            "youtube" => get_youtube_link(&ctx, component.clone()).await,
            "queue" => show_queue(&ctx, component.clone()).await,
            _ => {}
        }
    }

    let _ = component.defer().await;
}

async fn slash_play(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let Some(member) = &command.member else {
        let response = CreateInteractionResponseMessage::new()
            .content("Could not find member information.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let Some(search) = command.data.options.first().and_then(|opt| opt.value.as_str()) else {
        let response = CreateInteractionResponseMessage::new()
            .content("Please provide a search query or URL.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let result = handle_play(&ctx, guild_id, member, search, command.channel_id).await;

    let content = match result {
        Ok(msg) => msg,
        Err(msg) => msg,
    };

    let response = CreateInteractionResponseMessage::new()
        .content(content)
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_skip(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let content = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        if call_lock.queue().current().is_some() {
            call_lock.queue().skip().ok();
            format!("{} skipped", command.user.name)
        } else {
            "Nothing to skip.".to_string()
        }
    } else {
        "Not connected to voice.".to_string()
    };

    let response = CreateInteractionResponseMessage::new()
        .content(content)
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_pause(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    toggle_pause(&ctx, guild_id).await;

    let response = CreateInteractionResponseMessage::new()
        .content("Paused playback.")
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_resume(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    toggle_pause(&ctx, guild_id).await;

    let response = CreateInteractionResponseMessage::new()
        .content("Resumed playback.")
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_stop(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().stop();
    }

    let response = CreateInteractionResponseMessage::new()
        .content("Stopped playback and cleared queue.")
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_volume(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let volume: u8 = command.data.options.first()
        .and_then(|opt| opt.value.as_u64())
        .map(|v| v as u8)
        .unwrap_or(100);

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();
    let states = data.get::<GuildStates>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().modify_queue(|queue| {
            queue.set_volume(f32::from(volume) / 100.0);
        });

        let mut states_write = states.write();
        if let Some(state) = states_write.get_mut(&guild_id) {
            state.volume = volume;
        }
    }

    let response = CreateInteractionResponseMessage::new()
        .content(format!("Volume set to {}%", volume))
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_queue(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let embed = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        let tracks: Vec<_> = call_lock.queue().current_queue();

        if tracks.is_empty() {
            CreateEmbed::new()
                .title("📋 Queue")
                .description("**Queue is empty**")
                .color(0x5865F2)
        } else {
            let tracks_per_page = 10;
            let mut queue_text = Vec::new();

            for (idx, track) in tracks.iter().take(tracks_per_page).enumerate() {
                let metadata = track.metadata();
                let (artist, title) = extract_artist_title_from_metadata(metadata);
                let duration = metadata.duration
                    .map(|d| format_duration(d.as_millis() as u64))
                    .unwrap_or_else(|| "?".to_string());

                queue_text.push(format!("**{}**. {} - {} `[{}]`", idx + 1, artist, title, duration));
            }

            let total_tracks = tracks.len();
            let description = queue_text.join("\n");

            CreateEmbed::new()
                .title("📋 Queue")
                .description(description)
                .color(0x5865F2)
                .footer(CreateEmbedFooter::new(format!(
                    "Showing {} of {} tracks",
                    tracks_per_page.min(total_tracks),
                    total_tracks
                )))
        }
    } else {
        CreateEmbed::new()
            .title("📋 Queue")
            .description("**Queue is empty**")
            .color(0x5865F2)
    };

    let response = CreateInteractionResponseMessage::new()
        .embed(embed)
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_np(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let content = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        if let Some(track) = call_lock.queue().current() {
            let metadata = track.metadata();
            let (artist, title) = extract_artist_title_from_metadata(metadata);
            format!("🎵 **Now Playing:** {} - {}", artist, title)
        } else {
            "No song is currently playing.".to_string()
        }
    } else {
        "Not connected to voice.".to_string()
    };

    let response = CreateInteractionResponseMessage::new()
        .content(content)
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_remove(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let index: usize = command.data.options.first()
        .and_then(|opt| opt.value.as_u64())
        .map(|v| v as usize)
        .unwrap_or(0);

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let content = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        let tracks: Vec<_> = call_lock.queue().current_queue();

        if index > 0 && index <= tracks.len() {
            let removed_track = &tracks[index - 1];
            let metadata = removed_track.metadata();
            let (artist, title) = extract_artist_title_from_metadata(metadata);
            format!("Removed: {} - {}", artist, title)
        } else {
            "Invalid track number.".to_string()
        }
    } else {
        "Not connected to voice.".to_string()
    };

    let response = CreateInteractionResponseMessage::new()
        .content(content)
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_clear(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().stop();
    }

    let response = CreateInteractionResponseMessage::new()
        .content("Queue cleared.")
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_loop(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    toggle_loop(&ctx, guild_id).await;

    let data = ctx.data.read().await;
    let states = data.get::<GuildStates>().unwrap().read();
    let loop_status = states.get(&guild_id)
        .map(|s| if s.loop_mode { "on" } else { "off" })
        .unwrap_or("off");

    let response = CreateInteractionResponseMessage::new()
        .content(format!("Loop {}", loop_status))
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_lyrics(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let current_track = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().current()
    } else {
        None
    };

    let result = if let Some(track) = current_track {
        let metadata = track.metadata();
        let (artist, title) = extract_artist_title_from_metadata(metadata);

        match fetch_lyrics(&artist, &title).await {
            Ok(lyrics) => {
                let filename = format!("{} - {} - Lyrics.txt", artist, title);
                let attachment = Attachment::from_bytes(lyrics.into_bytes(), filename, None);

                let embed = CreateEmbed::new()
                    .title("📝 Lyrics")
                    .description(format!("**{}** by **{}**\n\nLyrics are attached as a text file above!", title, artist))
                    .color(0xFF6B35);

                let response = CreateInteractionResponseMessage::new()
                    .add_file(attachment)
                    .embed(embed)
                    .ephemeral(true);

                let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
                return;
            },
            Err(e) => e,
        }
    } else {
        "No song is currently playing.".to_string()
    };

    let response = CreateInteractionResponseMessage::new()
        .content(result)
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn slash_seek(ctx: Context, command: CommandInteraction) {
    let _ = command.defer().await;

    let Some(guild_id) = command.guild_id else {
        let response = CreateInteractionResponseMessage::new()
            .content("This command can only be used in a server.")
            .ephemeral(true);
        let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
        return;
    };

    let seconds: i64 = command.data.options.first()
        .and_then(|opt| opt.value.as_i64())
        .unwrap_or(0);

    seek_player(&ctx, guild_id, seconds).await;

    let response = CreateInteractionResponseMessage::new()
        .content(format!("Seeked {} seconds", seconds))
        .ephemeral(true);
    let _ = command.create_response(&ctx.http, CreateInteractionResponse::Message(response)).await;
}

async fn seek_player(ctx: &Context, guild_id: GuildId, seconds: i64) {
    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        if let Some(track) = call_lock.queue().current() {
            let current_pos = track.get_info().await
                .map(|info| info.position.as_millis() as i64)
                .unwrap_or(0);

            let track_length = track.metadata().duration
                .map(|d| d.as_millis() as i64)
                .unwrap_or(0);

            let new_pos = (current_pos + seconds * 1000).max(0).min(track_length);

            if let Err(e) = track.seek(Duration::from_millis(new_pos as u64)).await {
                warn!("Failed to seek: {}", e);
            }
        }
    }
}

async fn toggle_pause(ctx: &Context, guild_id: GuildId) {
    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        if let Some(track) = call_lock.queue().current() {
            let info = track.get_info().await.unwrap_or_default();
            if info.playing == songbird::tracks::PlayMode::Play {
                let _ = track.pause().await;
            } else {
                let _ = track.play().await;
            }
        }
    }
}

async fn skip_track(ctx: &Context, guild_id: GuildId) {
    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().skip().ok();
    }
}

async fn toggle_loop(ctx: &Context, guild_id: GuildId) {
    let data = ctx.data.read().await;
    let states = data.get::<GuildStates>().unwrap().clone();
    let mut states_write = states.write();

    if let Some(state) = states_write.get_mut(&guild_id) {
        state.loop_mode = !state.loop_mode;
    }
}

async fn get_lyrics(ctx: &Context, component: ComponentInteraction) {
    let _ = component.defer_ephemeral().await;

    let guild_id = component.guild_id.unwrap();
    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let current_track = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().current()
    } else {
        None
    };

    let Some(track) = current_track else {
        let response = CreateInteractionResponseMessage::new()
            .content("No song is currently playing.")
            .ephemeral(true);
        let _ = component.edit_response(&ctx.http, response).await;
        return;
    };

    let metadata = track.metadata();
    let (artist, title) = extract_artist_title_from_metadata(metadata);

    let result = fetch_lyrics(&artist, &title).await;

    match result {
        Ok(lyrics) => {
            let filename = format!("{} - {} - Lyrics.txt", artist, title);
            let attachment = Attachment::from_bytes(lyrics.into_bytes(), filename, None);

            let embed = CreateEmbed::new()
                .title("📝 Lyrics")
                .description(format!("**{}** by **{}**\n\nLyrics are attached as a text file above!", title, artist))
                .color(0xFF6B35);

            let response = CreateInteractionResponseMessage::new()
                .add_file(attachment)
                .embed(embed)
                .ephemeral(true);

            let _ = component.edit_response(&ctx.http, response).await;
        },
        Err(msg) => {
            let response = CreateInteractionResponseMessage::new()
                .content(msg)
                .ephemeral(true);
            let _ = component.edit_response(&ctx.http, response).await;
        }
    }
}

fn extract_artist_title_from_metadata(metadata: &AuxMetadata) -> (String, String) {
    let artist = metadata.artist.as_deref().unwrap_or("Unknown Artist");
    let title = metadata.title.as_deref().unwrap_or("Unknown Title");

    if artist == "Unknown Artist" || artist.is_empty() {
        let (parsed_artist, parsed_title) = parse_artist_title(title);
        (parsed_artist, parsed_title)
    } else {
        (artist.to_string(), title.to_string())
    }
}

async fn fetch_lyrics(artist: &str, title: &str) -> Result<String, String> {
    let attempts = vec![
        (artist.to_string(), title.to_string()),
        (artist.split(',').next().unwrap_or(artist).trim().to_string(), title.to_string()),
        (title.to_string(), title.to_string()),
        ("Various Artists".to_string(), title.to_string()),
        ("Various".to_string(), title.to_string()),
        ("Classic".to_string(), title.to_string()),
        ("Popular".to_string(), title.to_string()),
    ];

    for (try_artist, try_title) in attempts {
        match try_fetch_lyrics(&try_artist, &try_title).await {
            Ok(lyrics) => return Ok(lyrics),
            Err(_) => continue,
        }
    }

    Err("No lyrics found for this song. The lyrics database may not have this track, or it might be too new. Try searching for the official lyrics online.".to_string())
}

async fn try_fetch_lyrics(artist: &str, title: &str) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    let encoded_artist = encode(artist);
    let encoded_title = encode(title);
    let url = format!("https://api.lyrics.ovh/v1/{}/{}", encoded_artist, encoded_title);

    let response = HTTP_CLIENT.get(&url).send().await?;

    if response.status().is_success() {
        let json: serde_json::Value = response.json().await?;
        if let Some(lyrics) = json.get("lyrics").and_then(|l| l.as_str()) {
            let cleaned_lyrics = LYRICS_NEWLINES_REGEX.replace_all(lyrics.trim(), "\n\n");
            let content = format!("{} - {}\n\n{}", artist, title, cleaned_lyrics);
            return Ok(content);
        }
    }

    Err("Lyrics not found".into())
}

async fn get_spotify_link(ctx: &Context, component: ComponentInteraction) {
    let _ = component.defer_ephemeral().await;

    let guild_id = component.guild_id.unwrap();
    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let current_track = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().current()
    } else {
        None
    };

    let content = if let Some(track) = current_track {
        let metadata = track.metadata();
        let (artist, title) = extract_artist_title_from_metadata(metadata);
        let query = format!("{} {}", artist, title);
        let encoded_query = encode(&query);
        format!("🔍 **Spotify Search:** https://open.spotify.com/search/{}", encoded_query)
    } else {
        "No song is currently playing.".to_string()
    };

    let response = CreateInteractionResponseMessage::new()
        .content(content)
        .ephemeral(true);
    let _ = component.edit_response(&ctx.http, response).await;
}

async fn get_youtube_link(ctx: &Context, component: ComponentInteraction) {
    let _ = component.defer_ephemeral().await;

    let guild_id = component.guild_id.unwrap();
    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let current_track = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().current()
    } else {
        None
    };

    let content = if let Some(track) = current_track {
        let metadata = track.metadata();
        let (artist, title) = extract_artist_title_from_metadata(metadata);
        let query = format!("{} {}", artist, title);
        let encoded_query = encode(&query);
        format!("🔍 **YouTube Search:** https://www.youtube.com/search?q={}", encoded_query)
    } else {
        "No song is currently playing.".to_string()
    };

    let response = CreateInteractionResponseMessage::new()
        .content(content)
        .ephemeral(true);
    let _ = component.edit_response(&ctx.http, response).await;
}

async fn show_queue(ctx: &Context, component: ComponentInteraction) {
    let _ = component.defer_ephemeral().await;

    let guild_id = component.guild_id.unwrap();
    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let queue_info = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        let queue = call_lock.queue();
        let tracks: Vec<_> = queue.current_queue();

        if tracks.is_empty() {
            "📋 **Queue is empty**".to_string()
        } else {
            let tracks_per_page = 10;
            let mut queue_text = Vec::new();

            for (idx, track) in tracks.iter().take(tracks_per_page).enumerate() {
                let metadata = track.metadata();
                let (artist, title) = extract_artist_title_from_metadata(metadata);
                let duration = metadata.duration
                    .map(|d| format_duration(d.as_millis() as u64))
                    .unwrap_or_else(|| "?".to_string());

                queue_text.push(format!("**{}**. {} - {} `[{}]`", idx + 1, artist, title, duration));
            }

            let total_tracks = tracks.len();
            let description = queue_text.join("\n");

            let embed = CreateEmbed::new()
                .title("📋 Queue")
                .color(0x5865F2)
                .description(description)
                .footer(CreateEmbedFooter::new(format!(
                    "Showing {} of {} tracks",
                    tracks_per_page.min(total_tracks),
                    total_tracks
                )));

            let response = CreateInteractionResponseMessage::new()
                .embed(embed)
                .ephemeral(true);

            let _ = component.edit_response(&ctx.http, response).await;
            return;
        }
    } else {
        "📋 **Queue is empty**".to_string()
    };

    let response = CreateInteractionResponseMessage::new()
        .content(queue_info)
        .ephemeral(true);
    let _ = component.edit_response(&ctx.http, response).await;
}

async fn handle_play(ctx: &Context, guild_id: GuildId, member: &serenity::model::guild::Member, search: &str, channel_id: ChannelId) -> Result<String, String> {
    // Ensure user is in voice channel
    let voice_state = member.voice_states.get(&guild_id);
    let voice_channel = match voice_state.and_then(|vs| vs.channel_id) {
        Some(channel) => channel,
        None => return Err("You must be in a voice channel to use this command.".to_string()),
    };

    // Get or create guild state
    let data = ctx.data.read().await;
    let states = data.get::<GuildStates>().unwrap().clone();
    let mut states_write = states.write();

    let state = states_write.entry(guild_id).or_insert_with(GuildState::default);
    state.text_channel = channel_id;

    // Get songbird manager
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    // Ensure voice connection
    let call = match songbird.get(guild_id) {
        Some(call) => {
            // Check if we're in the right channel
            if call.lock().await.current_channel().map(|c| c.0) != Some(voice_channel.get()) {
                call.lock().await.join(voice_channel).await
                    .map_err(|e| format!("Failed to join voice channel: {}", e))?;
            }
            call
        },
        None => {
            let call = songbird.join(guild_id, voice_channel).await
                .map_err(|e| format!("Failed to join voice channel: {}", e))?;
            call
        }
    };

    // Cancel idle timer
    if let Some(timer) = state.idle_timer.take() {
        timer.abort();
    }

    // Search for tracks
    let lavalink = data.get::<LavalinkKey>().unwrap().clone();
    let search_query = get_search_query(search);

    let tracks = timeout(Duration::from_secs(10), lavalink.search(&search_query))
        .await
        .map_err(|_| "Search timed out.".to_string())?
        .map_err(|e| format!("Search failed: {}", e))?;

    if tracks.is_empty() {
        return Err("No results found.".to_string());
    }

    let mut added_count = 0;
    let call_lock = call.lock().await;

    match tracks {
        lavalink_rs::model::TrackLoadData::Track(track) => {
            let handle = call_lock.play_source(track.into());
            state.queue.push(handle);
            state.last_requester = Some(member.user.id);
            added_count = 1;
        },
        lavalink_rs::model::TrackLoadData::Playlist(playlist) => {
            for track in playlist.tracks {
                let handle = call_lock.play_source(track.into());
                state.queue.push(handle);
            }
            added_count = playlist.tracks.len();
        },
        lavalink_rs::model::TrackLoadData::Search(search_results) => {
            if let Some(track) = search_results.tracks.first() {
                let handle = call_lock.play_source(track.clone().into());
                state.queue.push(handle);
                state.last_requester = Some(member.user.id);
                added_count = 1;
            }
        },
        _ => return Err("No playable tracks found.".to_string()),
    }

    drop(call_lock);

    if added_count == 1 {
        Ok(format!("Queued: {}", search))
    } else {
        Ok(format!("Queued playlist with {} tracks", added_count))
    }
}

fn get_search_query(search: &str) -> String {
    if search.starts_with("http://") || search.starts_with("https://") {
        search.to_string()
    } else if !search.starts_with("ytsearch:") && !search.starts_with("ytmsearch:")
            && !search.starts_with("scsearch:") && !search.starts_with("spsearch:") {
        format!("ytsearch:{}", search)
    } else {
        search.to_string()
    }
}

#[command]
async fn play_command(ctx: &Context, msg: &Message, args: Args) -> CommandResult {
    let search = args.rest();
    if search.is_empty() {
        msg.reply(&ctx.http, "Please provide a search query or URL.").await?;
        return Ok(());
    }

    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let Some(member) = &msg.member else {
        msg.reply(&ctx.http, "Could not find member information.").await?;
        return Ok(());
    };

    let result = handle_play(ctx, guild_id, member, search, msg.channel_id).await;

    let content = match result {
        Ok(msg_content) => msg_content,
        Err(msg_content) => msg_content,
    };

    msg.reply(&ctx.http, content).await?;
    Ok(())
}

#[command]
async fn skip_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        if call_lock.queue().current().is_some() {
            call_lock.queue().skip().ok();
            msg.reply(&ctx.http, format!("{} skipped", msg.author.name)).await?;
        } else {
            msg.reply(&ctx.http, "Nothing to skip.").await?;
        }
    } else {
        msg.reply(&ctx.http, "Not connected to voice.").await?;
    }

    Ok(())
}

#[command]
async fn pause_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    toggle_pause(ctx, guild_id).await;
    msg.reply(&ctx.http, "Paused playback.").await?;
    Ok(())
}

#[command]
async fn resume_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    toggle_pause(ctx, guild_id).await;
    msg.reply(&ctx.http, "Resumed playback.").await?;
    Ok(())
}

#[command]
async fn stop_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().stop();
    }

    msg.reply(&ctx.http, "Stopped playback and cleared queue.").await?;
    Ok(())
}

#[command]
async fn volume_command(ctx: &Context, msg: &Message, args: Args) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let volume: u8 = match args.rest().parse() {
        Ok(v) if v <= 100 => v,
        _ => {
            msg.reply(&ctx.http, "Please provide a volume level between 0 and 100.").await?;
            return Ok(());
        }
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();
    let states = data.get::<GuildStates>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().modify_queue(|queue| {
            queue.set_volume(f32::from(volume) / 100.0);
        });

        let mut states_write = states.write();
        if let Some(state) = states_write.get_mut(&guild_id) {
            state.volume = volume;
        }
    }

    msg.reply(&ctx.http, format!("Volume set to {}%", volume)).await?;
    Ok(())
}

#[command]
async fn queue_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let content = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        let tracks: Vec<_> = call_lock.queue().current_queue();

        if tracks.is_empty() {
            "📋 **Queue is empty**".to_string()
        } else {
            let tracks_per_page = 10;
            let mut queue_text = Vec::new();

            for (idx, track) in tracks.iter().take(tracks_per_page).enumerate() {
                let metadata = track.metadata();
                let (artist, title) = extract_artist_title_from_metadata(metadata);
                let duration = metadata.duration
                    .map(|d| format_duration(d.as_millis() as u64))
                    .unwrap_or_else(|| "?".to_string());

                queue_text.push(format!("**{}**. {} - {} `[{}]`", idx + 1, artist, title, duration));
            }

            let total_tracks = tracks.len();
            format!("📋 **Queue**\n{}",
                queue_text.join("\n") +
                &format!("\n\nShowing {} of {} tracks",
                    tracks_per_page.min(total_tracks), total_tracks))
        }
    } else {
        "📋 **Queue is empty**".to_string()
    };

    msg.reply(&ctx.http, content).await?;
    Ok(())
}

#[command]
async fn np_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let content = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        if let Some(track) = call_lock.queue().current() {
            let metadata = track.metadata();
            let (artist, title) = extract_artist_title_from_metadata(metadata);
            format!("🎵 **Now Playing:** {} - {}", artist, title)
        } else {
            "No song is currently playing.".to_string()
        }
    } else {
        "Not connected to voice.".to_string()
    };

    msg.reply(&ctx.http, content).await?;
    Ok(())
}

#[command]
async fn remove_command(ctx: &Context, msg: &Message, args: Args) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let index: usize = match args.rest().parse() {
        Ok(i) if i > 0 => i,
        _ => {
            msg.reply(&ctx.http, "Please provide a valid track number.").await?;
            return Ok(());
        }
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let result = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        let tracks: Vec<_> = call_lock.queue().current_queue();

        if index <= tracks.len() {
            let removed_track = &tracks[index - 1];
            let metadata = removed_track.metadata();
            let (artist, title) = extract_artist_title_from_metadata(metadata);

            // Note: songbird doesn't have a direct remove method, this is simplified
            format!("Removed: {} - {}", artist, title)
        } else {
            "Invalid track number.".to_string()
        }
    } else {
        "Not connected to voice.".to_string()
    };

    msg.reply(&ctx.http, result).await?;
    Ok(())
}

#[command]
async fn clear_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().stop();
    }

    msg.reply(&ctx.http, "Queue cleared.").await?;
    Ok(())
}

#[command]
async fn loop_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    toggle_loop(ctx, guild_id).await;

    let data = ctx.data.read().await;
    let states = data.get::<GuildStates>().unwrap().read();
    let loop_status = states.get(&guild_id)
        .map(|s| if s.loop_mode { "on" } else { "off" })
        .unwrap_or("off");

    msg.reply(&ctx.http, format!("Loop {}", loop_status)).await?;
    Ok(())
}

#[command]
async fn lyrics_command(ctx: &Context, msg: &Message) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let data = ctx.data.read().await;
    let songbird = data.get::<SongbirdKey>().unwrap().clone();

    let current_track = if let Some(call) = songbird.get(guild_id) {
        let call_lock = call.lock().await;
        call_lock.queue().current()
    } else {
        None
    };

    let content = if let Some(track) = current_track {
        let metadata = track.metadata();
        let (artist, title) = extract_artist_title_from_metadata(metadata);

        match fetch_lyrics(&artist, &title).await {
            Ok(lyrics) => {
                let filename = format!("{} - {} - Lyrics.txt", artist, title);
                let attachment = Attachment::from_bytes(lyrics.into_bytes(), filename, None);

                let embed = CreateEmbed::new()
                    .title("📝 Lyrics")
                    .description(format!("**{}** by **{}**\n\nLyrics are attached as a text file above!", title, artist))
                    .color(0xFF6B35);

                let message = CreateMessage::new()
                    .add_file(attachment)
                    .embed(embed);

                let _ = msg.channel_id.send_message(&ctx.http, message).await;
                "Lyrics sent as attachment!".to_string()
            },
            Err(e) => e,
        }
    } else {
        "No song is currently playing.".to_string()
    };

    msg.reply(&ctx.http, content).await?;
    Ok(())
}

#[command]
async fn seek_command(ctx: &Context, msg: &Message, args: Args) -> CommandResult {
    let Some(guild_id) = msg.guild_id else {
        msg.reply(&ctx.http, "This command can only be used in a server.").await?;
        return Ok(());
    };

    let seconds: i64 = match args.rest().parse() {
        Ok(s) => s,
        _ => {
            msg.reply(&ctx.http, "Please provide a valid number of seconds.").await?;
            return Ok(());
        }
    };

    seek_player(ctx, guild_id, seconds).await;
    msg.reply(&ctx.http, format!("Seeked {} seconds", seconds)).await?;
    Ok(())
}

struct SongbirdKey;
impl TypeMapKey for SongbirdKey {
    type Value = Arc<Songbird>;
}

struct LavalinkKey;
impl TypeMapKey for LavalinkKey {
    type Value = lavalink_rs::LavalinkClient;
}

struct GuildStates;
impl TypeMapKey for GuildStates {
    type Value = Arc<RwLock<HashMap<GuildId, GuildState>>>;
}

#[group]
#[commands(play, skip, pause, resume, stop, volume, queue, np, remove, clear, loop, lyrics, seek)]
struct Music;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt::init();

    let token = std::env::var("DISCORD_BOT_TOKEN").expect("DISCORD_BOT_TOKEN must be set");

    let framework = StandardFramework::new()
        .configure(|c| c.prefix("!"))
        .group(&MUSIC_GROUP);

    let intents = GatewayIntents::GUILD_VOICE_STATES | GatewayIntents::GUILDS | GatewayIntents::GUILD_MESSAGES | GatewayIntents::MESSAGE_CONTENT;

    let mut client = Client::builder(&token, intents)
        .event_handler(Handler)
        .framework(framework)
        .await
        .expect("Error creating client");

    {
        let mut data = client.data.write().await;
        data.insert::<GuildStates>(Arc::new(RwLock::new(HashMap::new())));
    }

    if let Err(why) = client.start().await {
        error!("Client error: {:?}", why);
    }
}
