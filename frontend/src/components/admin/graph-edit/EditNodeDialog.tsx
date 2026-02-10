import { useState, useRef, useEffect } from 'react';
import { Loader2, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { RenameImpactPreview } from './RenameImpactPreview';
import { useUpdateNode, useRenameImpact } from '@/api/hooks/admin/useGraphEdit';
import { getApiErrorMessage } from '@/api/utils';
import type { NodeResponse } from '@/types/graphEdit';

interface PropertyRow {
  key: string;
  value: string;
  isNew?: boolean;
}

const RENAME_DEBOUNCE_MS = 500;

interface EditNodeDialogProps {
  node: NodeResponse | null;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (properties: Record<string, unknown>) => void;
}

function EditNodeForm({
  node,
  onOpenChange,
  onSuccess,
}: {
  node: NodeResponse;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (properties: Record<string, unknown>) => void;
}) {
  const [properties, setProperties] = useState<PropertyRow[]>(() =>
    Object.entries(node.properties).map(([key, value]) => ({
      key,
      value: String(value ?? ''),
    }))
  );
  const [error, setError] = useState<string | null>(null);

  const updateNode = useUpdateNode();
  const renameImpactMutation = useRenameImpact();

  // Keep ref to mutation — updated in effect, accessed only in event handlers/timeouts
  const renameRef = useRef(renameImpactMutation);
  useEffect(() => {
    renameRef.current = renameImpactMutation;
  }, [renameImpactMutation]);

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const originalName = String(node.properties.name || '');

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      clearTimeout(debounceTimerRef.current);
    };
  }, []);

  // Debounced rename impact check — called from event handler only
  const scheduleRenameCheck = (newName: string) => {
    clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      if (newName && newName !== originalName) {
        renameRef.current.mutate(
          { nodeId: node.id, new_name: newName },
          {
            onError: () => {
              setError('Failed to check rename impact');
            },
          }
        );
      } else {
        renameRef.current.reset();
      }
    }, RENAME_DEBOUNCE_MS);
  };

  const handlePropertyChange = (index: number, field: 'key' | 'value', newValue: string) => {
    const updated = [...properties];
    updated[index] = { ...updated[index], [field]: newValue };
    setProperties(updated);

    // Trigger debounced rename impact check when name changes
    if (field === 'value' && updated[index].key === 'name') {
      scheduleRenameCheck(newValue);
    }
  };

  const handleAddProperty = () => {
    setProperties([...properties, { key: '', value: '', isNew: true }]);
  };

  const handleRemoveProperty = (index: number) => {
    setProperties(properties.filter((_, i) => i !== index));
  };

  const handleSave = () => {
    // Cancel any pending rename impact check to avoid race condition
    clearTimeout(debounceTimerRef.current);
    renameImpactMutation.reset();
    setError(null);
    const newProperties: Record<string, unknown> = {};

    for (const prop of properties) {
      if (prop.key.trim()) {
        newProperties[prop.key.trim()] = prop.value;
      }
    }

    const currentKeys = new Set(properties.map((p) => p.key.trim()).filter(Boolean));
    for (const originalKey of Object.keys(node.properties)) {
      if (!currentKeys.has(originalKey)) {
        newProperties[originalKey] = null;
      }
    }

    updateNode.mutate(
      { nodeId: node.id, request: { properties: newProperties } },
      {
        onSuccess: () => {
          onSuccess?.(newProperties);
          onOpenChange(false);
        },
        onError: (err) => {
          setError(getApiErrorMessage(err));
        },
      }
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Edit Node</DialogTitle>
        <DialogDescription>
          Editing {node.labels.join(', ')} node: {String(node.properties.name || node.id)}
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-2">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-medium">Properties</h4>
            <Button variant="outline" size="sm" onClick={handleAddProperty}>
              <Plus className="mr-1 h-3 w-3" />
              Add
            </Button>
          </div>

          <div className="space-y-2">
            {properties.map((prop, index) => (
              <div key={index} className="flex items-center gap-2">
                <Input
                  value={prop.key}
                  onChange={(e) => handlePropertyChange(index, 'key', e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Key"
                  className="w-1/3"
                  disabled={!prop.isNew && prop.key === 'name'}
                />
                <Input
                  value={prop.value}
                  onChange={(e) => handlePropertyChange(index, 'value', e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Value"
                  className="flex-1"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-red-600"
                  onClick={() => handleRemoveProperty(index)}
                  disabled={prop.key === 'name'}
                  title={prop.key === 'name' ? 'Name property cannot be removed' : 'Remove property'}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </div>

        {renameImpactMutation.isPending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Checking rename impact...
          </div>
        )}
        {!renameImpactMutation.isPending && renameImpactMutation.data && (
          <RenameImpactPreview impact={renameImpactMutation.data} />
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
            {error}
          </div>
        )}
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button onClick={handleSave} disabled={updateNode.isPending}>
          {updateNode.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : (
            'Save Changes'
          )}
        </Button>
      </DialogFooter>
    </>
  );
}

export function EditNodeDialog({ node, onOpenChange, onSuccess }: EditNodeDialogProps) {
  return (
    <Dialog open={!!node} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        {node && <EditNodeForm key={node.id} node={node} onOpenChange={onOpenChange} onSuccess={onSuccess} />}
      </DialogContent>
    </Dialog>
  );
}
