import { useState } from 'react';
import { Loader2, Plus, X } from 'lucide-react';
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
import { useSchemaInfo, useCreateNode } from '@/api/hooks/admin/useGraphEdit';
import { getApiErrorMessage } from '@/api/utils';

interface PropertyRow {
  key: string;
  value: string;
}

interface CreateNodeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateNodeDialog({ open, onOpenChange }: CreateNodeDialogProps) {
  const [label, setLabel] = useState('');
  const [name, setName] = useState('');
  const [extraProperties, setExtraProperties] = useState<PropertyRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const { data: schema } = useSchemaInfo();
  const createNode = useCreateNode();

  const handleCreate = () => {
    if (!label || !name.trim()) return;
    setError(null);

    const properties: Record<string, unknown> = { name: name.trim() };
    for (const prop of extraProperties) {
      if (prop.key.trim()) {
        properties[prop.key.trim()] = prop.value;
      }
    }

    createNode.mutate(
      { label, properties },
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
    if (createNode.isPending) return;
    setLabel('');
    setName('');
    setExtraProperties([]);
    setError(null);
    onOpenChange(false);
  };

  const handleAddProperty = () => {
    setExtraProperties([...extraProperties, { key: '', value: '' }]);
  };

  const handleRemoveProperty = (index: number) => {
    setExtraProperties(extraProperties.filter((_, i) => i !== index));
  };

  const handlePropertyChange = (index: number, field: 'key' | 'value', newValue: string) => {
    const updated = [...extraProperties];
    updated[index] = { ...updated[index], [field]: newValue };
    setExtraProperties(updated);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return;
  };

  const requiredProps = label && schema?.required_properties[label]
    ? schema.required_properties[label].filter((p) => p !== 'name')
    : [];

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Node</DialogTitle>
          <DialogDescription>
            Create a new node in the knowledge graph
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Label Select */}
          <div className="space-y-2">
            <label htmlFor="node-label" className="text-sm font-medium">
              Label
            </label>
            <Select
              id="node-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            >
              <option value="">Select a label...</option>
              {schema?.allowed_labels.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </Select>
          </div>

          {/* Name Input */}
          <div className="space-y-2">
            <label htmlFor="node-name" className="text-sm font-medium">
              Name <span className="text-red-500">*</span>
            </label>
            <Input
              id="node-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter node name..."
            />
          </div>

          {/* Required Properties Hint */}
          {requiredProps.length > 0 && (
            <p className="text-sm text-muted-foreground">
              Required properties for {label}: {requiredProps.join(', ')}
            </p>
          )}

          {/* Extra Properties */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium">Additional Properties</h4>
              <Button variant="outline" size="sm" onClick={handleAddProperty}>
                <Plus className="mr-1 h-3 w-3" />
                Add
              </Button>
            </div>
            {extraProperties.map((prop, index) => (
              <div key={index} className="flex items-center gap-2">
                <Input
                  value={prop.key}
                  onChange={(e) => handlePropertyChange(index, 'key', e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Key"
                  className="w-1/3"
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
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

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
            disabled={!label || !name.trim() || createNode.isPending}
          >
            {createNode.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating...
              </>
            ) : (
              'Create Node'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
