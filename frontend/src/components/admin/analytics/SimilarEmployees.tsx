import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useFindSimilarEmployees } from '@/api/hooks/admin/useAnalytics';
import { Search, Loader2, User } from 'lucide-react';
import type { SimilarEmployeesResponse } from '@/types/admin';

export function SimilarEmployees() {
  const [employeeName, setEmployeeName] = useState('');
  const [topK] = useState(10);
  const [result, setResult] = useState<SimilarEmployeesResponse | null>(null);

  const findSimilar = useFindSimilarEmployees();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!employeeName.trim()) return;

    findSimilar.mutate(
      { employee_name: employeeName.trim(), top_k: topK },
      {
        onSuccess: (data) => setResult(data),
      }
    );
  };

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-lg">Find Similar Employees</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Search Form */}
        <form onSubmit={handleSearch} className="flex items-end gap-4">
          <div className="flex-1 space-y-2">
            <label htmlFor="employeeName" className="text-sm font-medium">
              Employee Name
            </label>
            <Input
              id="employeeName"
              value={employeeName}
              onChange={(e) => setEmployeeName(e.target.value)}
              placeholder="Enter employee name..."
            />
          </div>
          <Button type="submit" disabled={findSimilar.isPending || !employeeName.trim()}>
            {findSimilar.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Search className="mr-2 h-4 w-4" />
            )}
            Search
          </Button>
        </form>

        {/* Error */}
        {findSimilar.error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700" role="alert">
            {findSimilar.error instanceof Error
              ? findSimilar.error.message
              : 'Failed to find similar employees'}
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-4 pt-4 border-t">
            <p className="text-sm text-muted-foreground">
              Employees similar to <span className="font-medium text-foreground">{result.base_employee}</span>
            </p>

            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {result.similar_employees.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">No similar employees found</p>
              ) : (
                result.similar_employees.map((emp, index) => (
                  <div key={emp.name} className="flex items-center gap-3 rounded-lg border p-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-sm font-medium">
                      {index + 1}
                    </div>
                    <User className="h-4 w-4 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium">{emp.name}</p>
                      {emp.job_type && (
                        <p className="text-sm text-muted-foreground">{emp.job_type}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{emp.shared_skills} skills</Badge>
                      <Badge variant="secondary">{(emp.similarity * 100).toFixed(0)}%</Badge>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
