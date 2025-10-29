function ToggleSwitch({ enabled, onChange, disabled = false }) {
  return (
    <button
      onClick={() => !disabled && onChange(!enabled)}
      disabled={disabled}
      className={`
        relative inline-flex h-8 w-14 items-center rounded-full
        transition-colors duration-300 ease-in-out
        ${enabled ? 'bg-primary' : 'bg-gray-600'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:opacity-90'}
      `}
    >
      <span
        className={`
          inline-block h-6 w-6 transform rounded-full bg-white
          transition-transform duration-300 ease-in-out shadow-lg
          ${enabled ? 'translate-x-7' : 'translate-x-1'}
        `}
      />
    </button>
  )
}

export default ToggleSwitch

