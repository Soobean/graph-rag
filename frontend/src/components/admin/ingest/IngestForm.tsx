import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Upload, Loader2 } from 'lucide-react';
import { useStartIngest } from '@/api/hooks/admin/useIngest';
import type { SourceType } from '@/types/admin';

export function IngestForm() {
  const [filePath, setFilePath] = useState('');
  const [sourceType, setSourceType] = useState<SourceType>('csv');
  const [sheetName, setSheetName] = useState('');
  const [batchSize, setBatchSize] = useState(10);

  const startIngest = useStartIngest();

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
          <div className="grid gap-4 md:grid-cols-2">
            {/* File Path */}
            <div className="space-y-2">
              <label htmlFor="filePath" className="text-sm font-medium">
                File Path
              </label>
              <Input
                id="filePath"
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
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
          {startIngest.error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700" role="alert">
              {startIngest.error instanceof Error
                ? startIngest.error.message
                : 'Failed to start ingestion'}
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
