import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, Pencil, Trash2, Eye } from 'lucide-react';
import type { NodeResponse } from '@/types/graphEdit';

function getLabelBadgeVariant(label: string) {
  switch (label) {
    case 'Employee':
      return 'default';
    case 'Skill':
      return 'secondary';
    case 'Concept':
      return 'outline';
    case 'Project':
      return 'success';
    case 'Department':
      return 'warning';
    default:
      return 'outline';
  }
}

function getNodeName(node: NodeResponse): string {
  return String(node.properties.name || node.properties.title || node.id);
}

function getDisplayProperties(node: NodeResponse): string {
  const skip = new Set(['name', 'title']);
  const entries = Object.entries(node.properties).filter(([k]) => !skip.has(k));
  if (entries.length === 0) return '-';
  return entries
    .slice(0, 3)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(', ');
}

interface NodeListTableProps {
  nodes: NodeResponse[];
  isLoading: boolean;
  onEdit: (node: NodeResponse) => void;
  onDelete: (node: NodeResponse) => void;
  onViewImpact: (node: NodeResponse) => void;
}

export function NodeListTable({
  nodes,
  isLoading,
  onEdit,
  onDelete,
  onViewImpact,
}: NodeListTableProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <p>No nodes found</p>
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Labels</TableHead>
          <TableHead>Properties</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {nodes.map((node) => (
          <TableRow key={node.id}>
            <TableCell className="font-medium">{getNodeName(node)}</TableCell>
            <TableCell>
              <div className="flex items-center gap-1">
                {node.labels.map((label) => (
                  <Badge
                    key={label}
                    variant={getLabelBadgeVariant(label) as 'default' | 'secondary' | 'outline' | 'success' | 'warning'}
                  >
                    {label}
                  </Badge>
                ))}
              </div>
            </TableCell>
            <TableCell className="text-sm text-muted-foreground max-w-[300px] truncate">
              {getDisplayProperties(node)}
            </TableCell>
            <TableCell className="text-right">
              <div className="flex items-center justify-end gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                  onClick={() => onViewImpact(node)}
                  title="View deletion impact"
                  aria-label={`View deletion impact for ${getNodeName(node)}`}
                >
                  <Eye className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                  onClick={() => onEdit(node)}
                  title="Edit node"
                  aria-label={`Edit ${getNodeName(node)}`}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50"
                  onClick={() => onDelete(node)}
                  title="Delete node"
                  aria-label={`Delete ${getNodeName(node)}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
