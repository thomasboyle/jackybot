import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

function CompressPage({ user, onLogout }) {
  const navigate = useNavigate()
  const [selectedFile, setSelectedFile] = useState(null)
  const [outputFormat, setOutputFormat] = useState('av1')
  const [isCompressing, setIsCompressing] = useState(false)
  const [compressionProgress, setCompressionProgress] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleFileSelect = (event) => {
    const file = event.target.files[0]
    if (file) {
      // Check file type
      const allowedTypes = ['video/mp4', 'video/quicktime']
      if (!allowedTypes.includes(file.type)) {
        setError('Please select an MP4 or MOV file')
        setSelectedFile(null)
        return
      }

      // Check file size (allow up to 1GB for large video processing)
      const maxSize = 1024 * 1024 * 1024 // 1GB
      if (file.size > maxSize) {
        setError(`File size must be under 1GB. Your file is ${formatFileSize(file.size)}.`)
        setSelectedFile(null)
        return
      }

      // Warning for very large files
      if (file.size > 500 * 1024 * 1024) { // 500MB
        console.warn(`Large file detected: ${formatFileSize(file.size)}. Processing may take significant time and require substantial RAM.`)
      }

      setSelectedFile(file)
      setError('')
      setSuccess('')
    }
  }

  const handleCompress = async () => {
    if (!selectedFile) {
      setError('Please select a video file first')
      return
    }

    setIsCompressing(true)
    setCompressionProgress('Initializing video processor...')
    setError('')
    setSuccess('')

    try {
      // Load FFmpeg.wasm
      setCompressionProgress('Loading FFmpeg.wasm...')
      const { FFmpeg } = await import('@ffmpeg/ffmpeg')
      const { fetchFile } = await import('@ffmpeg/util')

      const ffmpeg = new FFmpeg()
      await ffmpeg.load({
        coreURL: '/ffmpeg/ffmpeg-core.js',
        wasmURL: '/ffmpeg/ffmpeg-core.wasm',
        workerURL: '/ffmpeg/ffmpeg-core.worker.js',
      })

      setCompressionProgress('Reading video file...')

      // Write input file to FFmpeg virtual filesystem
      const inputFileName = 'input.' + selectedFile.name.split('.').pop().toLowerCase()
      ffmpeg.FS('writeFile', inputFileName, await fetchFile(selectedFile))

      setCompressionProgress('Analyzing video...')

      // Determine correct output filename based on format
      const outputFileName = outputFormat === 'av1' ? 'compressed_video.mp4' : 'compressed_video.avif'

      // Build FFmpeg command based on output format
      let ffmpegArgs
      if (outputFormat === 'av1') {
        ffmpegArgs = [
          '-i', inputFileName,
          '-t', '60', // Limit to 60 seconds
          '-c:v', 'libaom-av1', '-crf', '30', '-b:v', '0',
          '-c:a', 'libopus', '-b:a', '64k',
          '-vf', 'scale=-2:720', // Scale to 720p height, maintain aspect ratio
          '-y', outputFileName
        ]
      } else { // avif
        ffmpegArgs = [
          '-i', inputFileName,
          '-t', '60', // Limit to 60 seconds
          '-c:v', 'libaom-av1', '-crf', '35', '-b:v', '0',
          '-c:a', 'libopus', '-b:a', '48k',
          '-vf', 'scale=-2:480', // Scale to 480p for AVIF
          '-f', 'avif',
          '-y', outputFileName
        ]
      }

      setCompressionProgress('Compressing video...')
      await ffmpeg.run(...ffmpegArgs)

      setCompressionProgress('Processing complete...')

      // Read output file
      const outputData = ffmpeg.FS('readFile', outputFileName)

      // Check file size
      if (outputData.length > 8 * 1024 * 1024) { // 8MB
        throw new Error('Compressed video is still over 8MB. Try a shorter video or different format.')
      }

      setCompressionProgress('Preparing download...')

      // Create download link
      const mimeType = outputFormat === 'av1' ? 'video/mp4' : 'image/avif'
      const downloadName = outputFormat === 'av1' ? 'compressed_video.mp4' : 'compressed_video.avif'
      const blob = new Blob([outputData.buffer], { type: mimeType })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = downloadName
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      setSuccess('Video compressed successfully! Download completed.')
      setCompressionProgress('')
      setSelectedFile(null)

      // Reset file input
      const fileInput = document.getElementById('video-upload')
      if (fileInput) fileInput.value = ''

      // Clean up FFmpeg
      ffmpeg.FS('unlink', inputFileName)
      ffmpeg.FS('unlink', outputFileName)

    } catch (err) {
      console.error('Compression error:', err)
      setError(err.message || 'Video compression failed. Please try again.')
      setCompressionProgress('')
    } finally {
      setIsCompressing(false)
    }
  }

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  return (
    <div className="min-h-screen bg-gray-900">
      {/* Simple Navigation Header */}
      <div className="bg-gray-800 border-b border-gray-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate('/dashboard')}
              className="text-white hover:text-blue-400 transition-colors"
            >
              ← Back to Dashboard
            </button>
            <div className="text-xl font-bold text-white">🎥 Video Compression</div>
          </div>
          <div className="flex items-center space-x-4">
            <span className="text-gray-300">Welcome, {user?.username}</span>
            <button
              onClick={onLogout}
              className="text-red-400 hover:text-red-300 transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </div>

      <div className="p-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">🎥 Video Compression Tool</h1>
          <p className="text-gray-300">
            Compress your MP4 or MOV videos to under 8MB and 60 seconds max.
            All processing happens locally in your browser - your videos never leave your device!
          </p>
          <p className="text-sm text-blue-300 mt-2">
            💡 <strong>Tip:</strong> If you can't upload large files, try refreshing the page or clearing your browser cache.
            The current limit is 1GB for supported browsers.
          </p>
          </div>

          <div className="bg-gray-800 rounded-lg p-8 shadow-xl">
            <div className="space-y-6">
              {/* File Upload Section */}
              <div>
                <label className="block text-lg font-medium text-white mb-3">
                  Upload Video File
                </label>
                <div className="border-2 border-dashed border-gray-600 rounded-lg p-8 text-center hover:border-blue-500 transition-colors">
                  <input
                    id="video-upload"
                    type="file"
                    accept=".mp4,.mov,video/mp4,video/quicktime"
                    onChange={handleFileSelect}
                    className="hidden"
                    disabled={isCompressing}
                  />
                  <label htmlFor="video-upload" className="cursor-pointer">
                    <div className="text-6xl mb-4">📁</div>
                    <div className="text-gray-300 mb-2">
                      {selectedFile ? (
                        <div>
                          <div className="text-green-400 font-medium">{selectedFile.name}</div>
                          <div className="text-sm text-gray-400">{formatFileSize(selectedFile.size)}</div>
                        </div>
                      ) : (
                        'Click to select MP4 or MOV file'
                      )}
                    </div>
                    <div className="text-sm text-gray-500">
                      Maximum file size: 1GB • Supported: MP4, MOV
                    </div>
                  </label>
                </div>
              </div>

              {/* Format Selection */}
              <div>
                <label className="block text-lg font-medium text-white mb-3">
                  Output Format
                </label>
                <div className="grid grid-cols-2 gap-4">
                  <label className="relative">
                    <input
                      type="radio"
                      name="format"
                      value="av1"
                      checked={outputFormat === 'av1'}
                      onChange={(e) => setOutputFormat(e.target.value)}
                      className="sr-only peer"
                      disabled={isCompressing}
                    />
                    <div className="p-4 bg-gray-700 border-2 border-gray-600 rounded-lg cursor-pointer hover:border-blue-500 peer-checked:border-blue-500 peer-checked:bg-blue-900/20 transition-all">
                      <div className="text-white font-medium">AV1 (MP4)</div>
                      <div className="text-sm text-gray-400 mt-1">
                        Better compression, smaller file size, video format
                      </div>
                    </div>
                  </label>

                  <label className="relative">
                    <input
                      type="radio"
                      name="format"
                      value="avif"
                      checked={outputFormat === 'avif'}
                      onChange={(e) => setOutputFormat(e.target.value)}
                      className="sr-only peer"
                      disabled={isCompressing}
                    />
                    <div className="p-4 bg-gray-700 border-2 border-gray-600 rounded-lg cursor-pointer hover:border-blue-500 peer-checked:border-blue-500 peer-checked:bg-blue-900/20 transition-all">
                      <div className="text-white font-medium">AVIF</div>
                      <div className="text-sm text-gray-400 mt-1">
                        Alternative format, good compression, image sequence
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Compression Info */}
              <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4">
                <h3 className="text-blue-400 font-medium mb-2">Compression Details</h3>
                <ul className="text-sm text-gray-300 space-y-1">
                  <li>• Videos longer than 60 seconds will be trimmed</li>
                  <li>• Output will be under 8MB guaranteed</li>
                  <li>• Resolution will be optimized for file size</li>
                  <li>• Audio will be compressed to Opus format</li>
                  <li>• All processing happens locally in your browser</li>
                  <li>• Your videos never leave your device</li>
                  <li>• Large files (500MB+) may require significant RAM and time</li>
                  <li>• File size limit: 1GB (browser dependent)</li>
                </ul>
              </div>

              {/* Compress Button */}
              <button
                onClick={handleCompress}
                disabled={!selectedFile || isCompressing}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isCompressing ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                    Compressing...
                  </>
                ) : (
                  <>
                    <span>🎥</span>
                    Compress Video
                  </>
                )}
              </button>

              {/* Progress Messages */}
              {compressionProgress && (
                <div className="text-blue-400 text-center py-2">
                  {compressionProgress}
                </div>
              )}

              {/* Error Messages */}
              {error && (
                <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
                  <div className="text-red-400 font-medium">Error</div>
                  <div className="text-red-300 text-sm mt-1">{error}</div>
                </div>
              )}

              {/* Success Messages */}
              {success && (
                <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-4">
                  <div className="text-green-400 font-medium">Success!</div>
                  <div className="text-green-300 text-sm mt-1">{success}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default CompressPage
