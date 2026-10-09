import { useState } from 'react'
import { Upload, Layers, ShieldCheck, Loader2 } from 'lucide-react'
import axios from 'axios'
import clsx from 'clsx'
import { twMerge } from 'tailwind-merge'
import Dashboard from './Dashboard'

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs))
}

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [fileId, setFileId] = useState<string | null>(null)
  
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
    }
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0])
    }
  }

  const handleUpload = async () => {
    if (!file) return

    setIsUploading(true)
    setUploadProgress(0)
    
    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await axios.post('http://localhost:8000/api/v1/files/', formData, {
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / (progressEvent.total ?? 100))
          setUploadProgress(percentCompleted)
        }
      })
      
      setFileId(response.data.id)
    } catch (error) {
      console.error("Upload failed", error)
      alert("Upload failed. Make sure the backend is running.")
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-16 border-b border-border bg-surface/50 backdrop-blur flex items-center px-6 sticky top-0 z-50">
        <div className="flex items-center gap-3 text-primary">
          <Layers className="w-6 h-6" />
          <h1 className="text-xl font-bold tracking-tight text-text">GeoMeasure<span className="text-primary">X</span></h1>
        </div>
        <div className="ml-auto flex items-center gap-4 text-sm text-textDim font-medium">
          <span className="flex items-center gap-1.5"><ShieldCheck className="w-4 h-4 text-secondary" /> Secure Pipeline</span>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="hover:text-text transition-colors">API Docs</a>
        </div>
      </header>

      <main className="flex-1 p-6 lg:p-8 max-w-7xl mx-auto w-full flex flex-col gap-8">
        
        {!fileId && (
          <div className="max-w-2xl mx-auto w-full mt-12 flex flex-col gap-6">
            <div className="text-center space-y-3">
              <h2 className="text-4xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-primary to-accent">
                Intelligent Geospatial Engine
              </h2>
              <p className="text-textDim text-lg">
                Upload a KML or Shapefile ZIP to instantly calculate accurate metric areas and lengths using dynamic CRS resolution.
              </p>
            </div>

            <div 
              className={cn(
                "mt-8 p-12 border-2 border-dashed rounded-3xl flex flex-col items-center justify-center gap-4 transition-all duration-500 group bg-surfaceHighlight/20",
                file ? "border-primary bg-primary/5 shadow-[0_0_40px_rgba(224,108,83,0.15)]" : "border-border hover:border-primary/50 hover:bg-surfaceHighlight/40 hover:shadow-[0_0_30px_rgba(224,108,83,0.1)]"
              )}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              <div className="w-20 h-20 rounded-full bg-surfaceHighlight flex items-center justify-center text-primary mb-2 shadow-inner group-hover:animate-float group-hover:bg-primary/20 transition-all duration-500">
                <Upload className="w-10 h-10 group-hover:scale-110 transition-transform duration-500" />
              </div>
              
              <div className="text-center">
                {file ? (
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-lg font-medium text-primary">{file.name}</span>
                    <span className="text-sm text-textDim">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                  </div>
                ) : (
                  <>
                    <p className="text-lg font-medium">Drag & drop your file here</p>
                    <p className="text-sm text-textDim mt-1">Supports .kml and .zip (Shapefile)</p>
                  </>
                )}
              </div>

              <input 
                type="file" 
                id="file-upload" 
                className="hidden" 
                accept=".kml,.zip"
                onChange={handleFileChange}
              />
              
              <div className="flex gap-4 mt-6">
                <label htmlFor="file-upload" className="btn-secondary cursor-pointer">
                  Browse Files
                </label>
                {file && (
                  <button onClick={handleUpload} disabled={isUploading} className="btn-primary w-32">
                    {isUploading ? <Loader2 className="w-5 h-5 animate-spin" /> : 'Process File'}
                  </button>
                )}
              </div>
              
              {isUploading && (
                <div className="w-full max-w-sm mt-4 bg-surface rounded-full h-2 overflow-hidden border border-border">
                  <div 
                    className="bg-primary h-full transition-all duration-300 ease-out" 
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {fileId && (
          <div className="w-full">
            <Dashboard fileId={fileId} />
            
            <div className="mt-8 flex justify-center">
              <button 
                onClick={() => setFileId(null)} 
                className="btn-secondary"
              >
                Upload Another File
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
