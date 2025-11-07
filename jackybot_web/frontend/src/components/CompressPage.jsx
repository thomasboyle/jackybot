import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

function CompressPage({ user, onLogout }) {
  const navigate = useNavigate()
  const [selectedFile, setSelectedFile] = useState(null)
  const [conversionType, setConversionType] = useState('video') // 'video' or 'image'
  const [isConverting, setIsConverting] = useState(false)
  const [conversionProgress, setConversionProgress] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const handleFileSelect = (event) => {
    const file = event.target.files[0]
    if (file) {
      // Check file type based on conversion type
      let allowedTypes = []
      let maxSize = 0
      let sizeError = ''

      if (conversionType === 'video') {
        allowedTypes = ['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/webm']
        maxSize = 1024 * 1024 * 1024 // 1GB
        sizeError = 'File size must be under 1GB'
      } else if (conversionType === 'image') {
        allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp']
        maxSize = 50 * 1024 * 1024 // 50MB
        sizeError = 'File size must be under 50MB'
      }

      if (!allowedTypes.includes(file.type)) {
        const typeNames = conversionType === 'video' ? 'MP4, MOV, AVI, or WebM' : 'JPEG, PNG, WebP, GIF, or BMP'
        setError(`Please select a ${typeNames} file`)
        setSelectedFile(null)
        return
      }

      if (file.size > maxSize) {
        setError(`${sizeError}. Your file is ${formatFileSize(file.size)}.`)
        setSelectedFile(null)
        return
      }

      setSelectedFile(file)
      setError('')
      setSuccess('')
    }
  }

  const handleConvert = async () => {
    if (!selectedFile) {
      setError('Please select a file first')
      return
    }

    setIsConverting(true)
    setConversionProgress('Uploading file...')
    setError('')
    setSuccess('')

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = conversionType === 'video'
        ? await api.convertVideo(formData)
        : await api.convertImage(formData)

      setConversionProgress('Processing complete!')

      // Create download link
      const mimeType = conversionType === 'video' ? 'video/mp4' : 'image/avif'
      const extension = conversionType === 'video' ? 'mp4' : 'avif'
      const downloadName = `converted.${extension}`

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = downloadName
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      setSuccess(`${conversionType === 'video' ? 'Video' : 'Image'} converted successfully! Download completed.`)
      setConversionProgress('')
      setSelectedFile(null)

      // Reset file input
      const fileInput = document.getElementById('file-upload')
      if (fileInput) fileInput.value = ''

    } catch (err) {
      console.error('Conversion error:', err)

      let errorMessage = 'Conversion failed. Please try again.'

      if (err.response?.data?.error) {
        errorMessage = err.response.data.error
      } else if (err.message) {
        if (err.message.includes('NetworkError') || err.message.includes('fetch')) {
          errorMessage = 'Network error. Please check your connection and try again.'
        } else if (err.message.includes('timeout')) {
          errorMessage = 'Conversion timed out. The file may be too large or complex. Try a smaller file.'
        } else {
          errorMessage = err.message
        }
      } else if (err.status === 413) {
        errorMessage = 'File too large. Please select a smaller file.'
      } else if (err.status === 415) {
        errorMessage = 'Unsupported file format. Please check the supported formats.'
      } else if (err.status === 500) {
        errorMessage = 'Server error. The video may be corrupted or too complex. Try a different file.'
      }

      setError(errorMessage)
      setConversionProgress('')
    } finally {
      setIsConverting(false)
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
              ? Back to Dashboard
            </button>
            <div className="text-xl font-bold text-white">?? Media Converter</div>
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
            <h1 className="text-3xl font-bold text-white mb-2">?? Media Converter</h1>
            <p className="text-gray-300">
              Convert your videos to AV1 format or images to AVIF format.
              Files are processed on our secure servers for optimal performance and quality.
            </p>
          </div>

          <div className="bg-gray-800 rounded-lg p-8 shadow-xl">
            <div className="space-y-6">
              {/* Conversion Type Selection */}
              <div>
                <label className="block text-lg font-medium text-white mb-3">
                  Select Conversion Type
                </label>
                <div className="flex space-x-4">
                  <button
                    onClick={() => {
                      setConversionType('video')
                      setSelectedFile(null)
                      setError('')
                      setSuccess('')
                    }}
                    className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                      conversionType === 'video'
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    ?? Video to AV1
                  </button>
                  <button
                    onClick={() => {
                      setConversionType('image')
                      setSelectedFile(null)
                      setError('')
                      setSuccess('')
                    }}
                    className={`px-6 py-3 rounded-lg font-medium transition-colors ${
                      conversionType === 'image'
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }`}
                  >
                    ??? Image to AVIF
                  </button>
                </div>
              </div>

              {/* File Upload Section */}
              <div>
                <label className="block text-lg font-medium text-white mb-3">
                  Upload {conversionType === 'video' ? 'Video' : 'Image'} File
                </label>
                <div className="border-2 border-dashed border-gray-600 rounded-lg p-8 text-center hover:border-blue-500 transition-colors">
                  <input
                    id="file-upload"
                    type="file"
                    accept={conversionType === 'video'
                      ? ".mp4,.mov,.avi,.webm,video/mp4,video/quicktime,video/x-msvideo,video/webm"
                      : ".jpg,.jpeg,.png,.webp,.gif,.bmp,image/jpeg,image/png,image/webp,image/gif,image/bmp"
                    }
                    onChange={handleFileSelect}
                    className="hidden"
                    disabled={isConverting}
                  />
                  <label htmlFor="file-upload" className="cursor-pointer">
                    <div className="text-6xl mb-4">{conversionType === 'video' ? '??' : '???'}</div>
                    <div className="text-gray-300 mb-2">
                      {selectedFile ? (
                        <div>
                          <div className="text-green-400 font-medium">{selectedFile.name}</div>
                          <div className="text-sm text-gray-400">{formatFileSize(selectedFile.size)}</div>
                        </div>
                      ) : (
                        `Click to select ${conversionType === 'video' ? 'video' : 'image'} file`
                      )}
                    </div>
                    <div className="text-sm text-gray-500">
                      Maximum file size: {conversionType === 'video' ? '1GB' : '50MB'} ?
                      Supported: {conversionType === 'video' ? 'MP4, MOV, AVI, WebM' : 'JPEG, PNG, WebP, GIF, BMP'}
                    </div>
                  </label>
                </div>
              </div>

              {/* Output Info */}
              <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4">
                <h3 className="text-blue-400 font-medium mb-2">
                  Output Format: {conversionType === 'video' ? 'MP4 (AV1)' : 'AVIF'}
                </h3>
                <p className="text-sm text-gray-300">
                  {conversionType === 'video'
                    ? 'Videos will be converted to AV1 encoding for superior compression and quality while maintaining smaller file sizes.'
                    : 'Images will be converted to AVIF format for excellent compression with minimal quality loss.'
                  }
                </p>
              </div>

              {/* Conversion Info */}
              <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4">
                <h3 className="text-blue-400 font-medium mb-2">Conversion Details</h3>
                <ul className="text-sm text-gray-300 space-y-1">
                  {conversionType === 'video' ? (
                    <>
                      <li>? High-efficiency AV1 video encoding</li>
                      <li>? Optimized bitrate for quality and size balance</li>
                      <li>? Maintains original resolution when possible</li>
                      <li>? Preserves audio quality with efficient encoding</li>
                      <li>? Fast processing with server-side acceleration</li>
                    </>
                  ) : (
                    <>
                      <li>? Modern AVIF image format with superior compression</li>
                      <li>? Maintains high visual quality</li>
                      <li>? Supports transparency and animation</li>
                      <li>? Significant file size reduction</li>
                      <li>? Fast processing with server-side optimization</li>
                    </>
                  )}
                  <li>? Secure server-side processing</li>
                  <li>? Files are automatically deleted after conversion</li>
                </ul>
              </div>

              {/* Convert Button */}
              <button
                onClick={handleConvert}
                disabled={!selectedFile || isConverting}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isConverting ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                    Converting...
                  </>
                ) : (
                  <>
                    <span>{conversionType === 'video' ? '??' : '???'}</span>
                    Convert {conversionType === 'video' ? 'Video' : 'Image'}
                  </>
                )}
              </button>

              {/* Progress Messages */}
              {conversionProgress && (
                <div className="text-blue-400 text-center py-2">
                  {conversionProgress}
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
