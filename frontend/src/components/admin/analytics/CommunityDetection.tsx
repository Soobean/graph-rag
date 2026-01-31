import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useDetectCommunities } from '@/api/hooks/admin/useAnalytics';
import { Users, Loader2, Play } from 'lucide-react';
import type { CommunityDetectResponse } from '@/types/admin';

export function CommunityDetection() {
  const [algorithm, setAlgorithm] = useState<'leiden' | 'louvain'>('leiden');
  const [gamma, setGamma] = useState(1.0);
  const [result, setResult] = useState<CommunityDetectResponse | null>(null);

  const detectCommunities = useDetectCommunities();

  const handleDetect = () => {
    detectCommunities.mutate(
      { algorithm, gamma },
      {
        onSuccess: (data) => setResult(data),
      }
    );
  };

  return (
    <Card>
      <CardHeader className="pb-4">
        <CardTitle className="text-lg">Community Detection</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Controls */}
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-2">
            <label htmlFor="algorithm" className="text-sm font-medium">
              Algorithm
            </label>
            <Select
              id="algorithm"
              value={algorithm}
              onChange={(e) => setAlgorithm(e.target.value as 'leiden' | 'louvain')}
              className="w-32"
            >
              <option value="leiden">Leiden</option>
              <option value="louvain">Louvain</option>
            </Select>
          </div>
          <div className="space-y-2">
            <label htmlFor="gamma" className="text-sm font-medium">
              Resolution (gamma)
            </label>
            <Select
              id="gamma"
              value={String(gamma)}
              onChange={(e) => setGamma(parseFloat(e.target.value))}
              className="w-24"
            >
              <option value="0.5">0.5</option>
              <option value="1.0">1.0</option>
              <option value="1.5">1.5</option>
              <option value="2.0">2.0</option>
            </Select>
          </div>
          <Button onClick={handleDetect} disabled={detectCommunities.isPending}>
            {detectCommunities.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Detect
          </Button>
        </div>

        {/* Error */}
        {detectCommunities.error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700" role="alert">
            {detectCommunities.error instanceof Error
              ? detectCommunities.error.message
              : 'Failed to detect communities'}
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-4 pt-4 border-t">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Algorithm: {result.algorithm}</span>
              <Badge variant="outline">Modularity: {result.modularity.toFixed(3)}</Badge>
            </div>
            <p className="text-sm font-medium">{result.community_count} communities detected</p>

            <div className="space-y-3 max-h-[300px] overflow-y-auto">
              {result.communities.map((community) => (
                <div
                  key={community.community_id}
                  className="flex items-start gap-3 rounded-lg border p-3"
                >
                  <div className="rounded-full bg-primary/10 p-2">
                    <Users className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">Community {community.community_id}</span>
                      <Badge variant="secondary">{community.member_count} members</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground truncate">
                      {community.sample_members.join(', ')}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
