import { useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { useSchemaInfo, useNodeSearch, useCreateEdge } from '@/api/hooks/admin/useGraphEdit';
import { useDebounce } from '@/hooks/useDebounce';
import { getApiErrorMessage } from '@/api/utils';
import type { NodeResponse } from '@/types/graphEdit';

interface CreateEdgeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateEdgeDialog({ open, onOpenChange }: CreateEdgeDialogProps) {
  const [relationshipType, setRelationshipType] = useState('');
  const [sourceSearch, setSourceSearch] = useState('');
  const [targetSearch, setTargetSearch] = useState('');
  const [selectedSource, setSelectedSource] = useState<NodeResponse | null>(null);
  const [selectedTarget, setSelectedTarget] = useState<NodeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: schema } = useSchemaInfo();
  const createEdge = useCreateEdge();

  // Get valid source/target labels for the selected relationship type
  const validCombos = schema?.valid_relationships[relationshipType] || [];
  const validSourceLabels = [...new Set(validCombos.map((c) => c.source))];
  const validTargetLabels = [...new Set(validCombos.map((c) => c.target))];

  // Debounced search for source and target nodes
  const debouncedSourceSearch = useDebounce(sourceSearch, 300);
  const debouncedTargetSearch = useDebounce(targetSearch, 300);

  const sourceLabel = validSourceLabels.length === 1 ? validSourceLabels[0] : undefined;
  const targetLabel = validTargetLabels.length === 1 ? validTargetLabels[0] : undefined;

  const { data: sourceResults } = useNodeSearch(
    debouncedSourceSearch.length >= 1
      ? { search: debouncedSourceSearch, label: sourceLabel, limit: 10 }
      : { label: sourceLabel, limit: 10 },
    !!relationshipType
  );
  const { data: targetResults } = useNodeSearch(
    debouncedTargetSearch.length >= 1
      ? { search: debouncedTargetSearch, label: targetLabel, limit: 10 }
      : { label: targetLabel, limit: 10 },
    !!relationshipType
  );

  const handleRelTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setRelationshipType(e.target.value);
    // Reset selections when relationship type changes
    setSelectedSource(null);
    setSelectedTarget(null);
    setSourceSearch('');
    setTargetSearch('');
  };

  const handleCreate = () => {
    if (!selectedSource || !selectedTarget || !relationshipType) return;
    setError(null);

    createEdge.mutate(
      {
        source_id: selectedSource.id,
        target_id: selectedTarget.id,
        relationship_type: relationshipType,
      },
      {
        onSuccess: () => {
          handleClose();
        },
        onError: (err) => {
          setError(getApiErrorMessage(err));
        },
      }
    );
  };

  const handleClose = () => {
    if (createEdge.isPending) return;
    setRelationshipType('');
    setSourceSearch('');
    setTargetSearch('');
    setSelectedSource(null);
    setSelectedTarget(null);
    setError(null);
    onOpenChange(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
  };

  const relationshipTypes = schema ? Object.keys(schema.valid_relationships).sort() : [];

  // Filter node results to only show nodes with valid labels
  const filteredSourceNodes = (sourceResults?.nodes || []).filter(
    (n) => validSourceLabels.length === 0 || n.labels.some((l) => validSourceLabels.includes(l))
  );
  const filteredTargetNodes = (targetResults?.nodes || []).filter(
    (n) => validTargetLabels.length === 0 || n.labels.some((l) => validTargetLabels.includes(l))
  );

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Edge</DialogTitle>
          <DialogDescription>
            Create a relationship between two nodes
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Relationship Type */}
          <div className="space-y-2">
            <label htmlFor="rel-type" className="text-sm font-medium">
              Relationship Type
            </label>
            <Select
              id="rel-type"
              value={relationshipType}
              onChange={handleRelTypeChange}
            >
              <option value="">Select type...</option>
              {relationshipTypes.map((rt) => (
                <option key={rt} value={rt}>
                  {rt}
                </option>
              ))}
            </Select>
            {validCombos.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Valid: {validCombos.map((c) => `${c.source} \u2192 ${c.target}`).join(', ')}
              </p>
            )}
          </div>

          {/* Source Node */}
          <NodePicker
            label="Source Node"
            placeholder="Search source node..."
            searchValue={sourceSearch}
            onSearchChange={setSourceSearch}
            selectedNode={selectedSource}
            onSelect={setSelectedSource}
            nodes={filteredSourceNodes}
            onKeyDown={handleKeyDown}
            disabled={!relationshipType}
          />

          {/* Target Node */}
          <NodePicker
            label="Target Node"
            placeholder="Search target node..."
            searchValue={targetSearch}
            onSearchChange={setTargetSearch}
            selectedNode={selectedTarget}
            onSelect={setSelectedTarget}
            nodes={filteredTargetNodes}
            onKeyDown={handleKeyDown}
            disabled={!relationshipType}
          />
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!selectedSource || !selectedTarget || !relationshipType || createEdge.isPending}
          >
            {createEdge.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating...
              </>
            ) : (
              'Create Edge'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ============================================
// Node Picker sub-component
// ============================================

interface NodePickerProps {
  label: string;
  placeholder: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  selectedNode: NodeResponse | null;
  onSelect: (node: NodeResponse | null) => void;
  nodes: NodeResponse[];
  onKeyDown: (e: React.KeyboardEvent) => void;
  disabled?: boolean;
}

function NodePicker({
  label,
  placeholder,
  searchValue,
  onSearchChange,
  selectedNode,
  onSelect,
  nodes,
  onKeyDown,
  disabled,
}: NodePickerProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleSelect = (node: NodeResponse) => {
    onSelect(node);
    setIsOpen(false);
    onSearchChange(String(node.properties.name || node.id));
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">{label}</label>
      {selectedNode ? (
        <div className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
          <span className="font-medium">
            {String(selectedNode.properties.name || selectedNode.id)}
          </span>
          <span className="text-muted-foreground">
            ({selectedNode.labels.join(', ')})
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto h-6 w-6"
            onClick={() => {
              onSelect(null);
              onSearchChange('');
            }}
          >
            <span className="text-xs text-muted-foreground">Clear</span>
          </Button>
        </div>
      ) : (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchValue}
            onChange={(e) => {
              onSearchChange(e.target.value);
              setIsOpen(true);
            }}
            onFocus={() => setIsOpen(true)}
            onBlur={() => {
              setTimeout(() => setIsOpen(false), 200);
            }}
            onKeyDown={onKeyDown}
            placeholder={placeholder}
            className="pl-9"
            disabled={disabled}
            role="combobox"
            aria-expanded={isOpen && nodes.length > 0}
            aria-haspopup="listbox"
          />
          {isOpen && nodes.length > 0 && (
            <div
              role="listbox"
              className="absolute z-10 mt-1 w-full rounded-md border bg-background shadow-lg max-h-48 overflow-y-auto"
            >
              {nodes.map((node) => (
                <button
                  key={node.id}
                  type="button"
                  role="option"
                  aria-selected={false}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-accent text-left"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelect(node);
                  }}
                >
                  <span className="font-medium">
                    {String(node.properties.name || node.id)}
                  </span>
                  <span className="text-muted-foreground">
                    ({node.labels.join(', ')})
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
