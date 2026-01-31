import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ProjectionStatus } from '@/components/admin/analytics/ProjectionStatus';
import { CommunityDetection } from '@/components/admin/analytics/CommunityDetection';
import { SimilarEmployees } from '@/components/admin/analytics/SimilarEmployees';
import { TeamRecommend } from '@/components/admin/analytics/TeamRecommend';

export function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-muted-foreground">
          Graph analytics powered by Neo4j GDS (Graph Data Science)
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <ProjectionStatus />
        </div>
        <div className="lg:col-span-2">
          <Tabs defaultValue="community" className="w-full">
            <TabsList className="w-full justify-start">
              <TabsTrigger value="community">Communities</TabsTrigger>
              <TabsTrigger value="similar">Similar Employees</TabsTrigger>
              <TabsTrigger value="team">Team Recommend</TabsTrigger>
            </TabsList>
            <div className="mt-4">
              <TabsContent value="community" className="m-0">
                <CommunityDetection />
              </TabsContent>
              <TabsContent value="similar" className="m-0">
                <SimilarEmployees />
              </TabsContent>
              <TabsContent value="team" className="m-0">
                <TeamRecommend />
              </TabsContent>
            </div>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
