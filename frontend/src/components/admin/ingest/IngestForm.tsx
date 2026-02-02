import { useState, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Upload, Loader2, FileUp, X, CheckCircle2, File } from 'lucide-react';
import { useStartIngest, useUploadFile } from '@/api/hooks/admin/useIngest';
import type { SourceType } from '@/types/admin';

export function IngestForm() {
  const [filePath, setFilePath] = useState('');
  const [sourceType, setSourceType] = useState<SourceType>('csv');
  const [sheetName, setSheetName] = useState('');
  const [batchSize, setBatchSize] = useState(10);

  // 드래그앤드롭 상태
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<{
    name: string;
    size: number;
    path: string;
  } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const startIngest = useStartIngest();
  const uploadFile = useUploadFile();

  // 파일 크기 제한 (100MB)
  const MAX_FILE_SIZE = 100 * 1024 * 1024;

  // 파일 업로드 처리
  const handleFileUpload = useCallback(async (file: File) => {
    // 파일 크기 체크
    if (file.size > MAX_FILE_SIZE) {
      alert(`파일이 너무 큽니다. 최대 크기: 100MB\n현재 크기: ${(file.size / 1024 / 1024).toFixed(1)}MB`);
      return;
    }

    // 확장자 체크 (개선: 확장자로 끝나는지 확인)
    const fileName = file.name.toLowerCase();
    const validExtensions = ['.csv', '.xlsx', '.xls'];
    const isValidExtension = validExtensions.some(ext => fileName.endsWith(ext));

    if (!isValidExtension) {
      alert('CSV 또는 Excel 파일만 업로드 가능합니다.');
      return;
    }

    try {
      const result = await uploadFile.mutateAsync(file);
      setUploadedFile({
        name: result.file_name,
        size: result.file_size,
        path: result.file_path,
      });
      setFilePath(result.file_path);
      setSourceType(result.source_type);
    } catch (error) {
      const errorMessage = error instanceof Error
        ? error.message
        : '파일 업로드에 실패했습니다.';
      alert(errorMessage);
    }
  }, [uploadFile]);

  // 드래그 이벤트 핸들러
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  }, [handleFileUpload]);

  // 파일 선택 핸들러
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileUpload(files[0]);
    }
  }, [handleFileUpload]);

  // 업로드된 파일 제거
  const handleRemoveFile = useCallback(() => {
    setUploadedFile(null);
    setFilePath('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, []);

  // 파일 크기 포맷
  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!filePath.trim()) return;

    startIngest.mutate(
      {
        file_path: filePath.trim(),
        source_type: sourceType,
        sheet_name: sourceType === 'excel' && sheetName ? sheetName : undefined,
        batch_size: batchSize,
      },
      {
        onSuccess: () => {
          setFilePath('');
          setSheetName('');
          setUploadedFile(null);
          if (fileInputRef.current) {
            fileInputRef.current.value = '';
          }
        },
      }
    );
  };

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-lg">Start New Ingestion</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* 드래그앤드롭 영역 */}
          <div className="space-y-2">
            <label className="text-sm font-medium">File Upload</label>

            {/* 파일이 업로드되지 않았을 때: 드래그앤드롭 영역 */}
            {!uploadedFile ? (
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`
                  relative flex flex-col items-center justify-center
                  h-32 border-2 border-dashed rounded-lg cursor-pointer
                  transition-all duration-200
                  ${isDragging
                    ? 'border-blue-500 bg-blue-50 scale-[1.02]'
                    : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
                  }
                  ${uploadFile.isPending ? 'pointer-events-none opacity-60' : ''}
                `}
              >
                {uploadFile.isPending ? (
                  <>
                    <Loader2 className="h-8 w-8 text-blue-500 animate-spin mb-2" />
                    <p className="text-sm text-gray-500">업로드 중...</p>
                  </>
                ) : (
                  <>
                    <FileUp className={`h-8 w-8 mb-2 ${isDragging ? 'text-blue-500' : 'text-gray-400'}`} />
                    <p className="text-sm text-gray-500">
                      파일을 드래그하거나 <span className="text-blue-500 font-medium">클릭</span>하여 선택
                    </p>
                    <p className="text-xs text-gray-400 mt-1">CSV, Excel (.xlsx, .xls)</p>
                  </>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </div>
            ) : (
              /* 파일이 업로드되었을 때: 파일 정보 표시 (파란색 강조) */
              <div className="flex items-center gap-3 p-4 rounded-lg border-2 border-blue-500 bg-blue-50">
                <div className="flex items-center justify-center h-10 w-10 rounded-lg bg-blue-100">
                  <File className="h-5 w-5 text-blue-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-blue-600" />
                    <p className="text-sm font-medium text-blue-900 truncate">
                      {uploadedFile.name}
                    </p>
                  </div>
                  <p className="text-xs text-blue-600">
                    {formatFileSize(uploadedFile.size)} • 업로드 완료
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleRemoveFile}
                  className="p-1 rounded-full hover:bg-blue-200 transition-colors"
                >
                  <X className="h-4 w-4 text-blue-600" />
                </button>
              </div>
            )}
          </div>

          {/* 또는 직접 경로 입력 */}
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white px-2 text-gray-500">또는 서버 경로 직접 입력</span>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {/* File Path */}
            <div className="space-y-2">
              <label htmlFor="filePath" className="text-sm font-medium">
                File Path
              </label>
              <Input
                id="filePath"
                value={filePath}
                onChange={(e) => {
                  setFilePath(e.target.value);
                  if (uploadedFile) setUploadedFile(null);
                }}
                placeholder="/path/to/data.csv"
                required
              />
            </div>

            {/* Source Type */}
            <div className="space-y-2">
              <label htmlFor="sourceType" className="text-sm font-medium">
                Source Type
              </label>
              <Select
                id="sourceType"
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as SourceType)}
              >
                <option value="csv">CSV</option>
                <option value="excel">Excel</option>
              </Select>
            </div>
          </div>

          {/* Excel Options */}
          {sourceType === 'excel' && (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="sheetName" className="text-sm font-medium">
                  Sheet Name (optional)
                </label>
                <Input
                  id="sheetName"
                  value={sheetName}
                  onChange={(e) => setSheetName(e.target.value)}
                  placeholder="Sheet1"
                />
              </div>
            </div>
          )}

          {/* Advanced Options */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label htmlFor="batchSize" className="text-sm font-medium">
                Batch Size
              </label>
              <Input
                id="batchSize"
                type="number"
                min={1}
                max={100}
                value={batchSize}
                onChange={(e) => {
                  const value = parseInt(e.target.value, 10);
                  setBatchSize(Number.isNaN(value) ? 10 : Math.min(Math.max(value, 1), 100));
                }}
              />
            </div>
          </div>

          {/* Error Message */}
          {(startIngest.error || uploadFile.error) && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700" role="alert">
              {startIngest.error instanceof Error
                ? startIngest.error.message
                : uploadFile.error instanceof Error
                ? uploadFile.error.message
                : 'An error occurred'}
            </div>
          )}

          {/* Success Message */}
          {startIngest.data && (
            <div className="rounded-md bg-green-50 p-3 text-sm text-green-700">
              Job started successfully! ID: {startIngest.data.job_id}
            </div>
          )}

          {/* Submit Button */}
          <div className="flex justify-end">
            <Button type="submit" disabled={startIngest.isPending || !filePath.trim()}>
              {startIngest.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              Start Ingestion
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
