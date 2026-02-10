import { useState } from 'react';
import { Select } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';
import { useDebounce } from '@/hooks/useDebounce';
import { useSchemaInfo } from '@/api/hooks/admin/useGraphEdit';
import type { NodeSearchParams } from '@/types/graphEdit';

interface NodeSearchFiltersProps {
  filters: NodeSearchParams;
  onFiltersChange: (filters: NodeSearchParams) => void;
}

const SEARCH_DEBOUNCE_MS = 300;

export function NodeSearchFilters({ filters, onFiltersChange }: NodeSearchFiltersProps) {
  const [searchValue, setSearchValue] = useState(filters.search || '');
  const { data: schema } = useSchemaInfo();

  const debouncedSearchValue = useDebounce(searchValue, SEARCH_DEBOUNCE_MS);

  // Sync debounced value to filters when it changes
  // This is safe because useDebounce returns a stable value until the delay elapses
  const appliedSearch = filters.search || '';
  if (debouncedSearchValue !== appliedSearch) {
    onFiltersChange({
      ...filters,
      search: debouncedSearchValue || undefined,
    });
  }

  const handleLabelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    onFiltersChange({
      ...filters,
      label: value === 'all' ? undefined : value,
    });
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchValue(e.target.value);
  };

  return (
    <div className="flex flex-wrap items-center gap-4">
      {/* Label Filter */}
      <div className="flex items-center gap-2">
        <label htmlFor="label-filter" className="text-sm font-medium">
          Label:
        </label>
        <Select
          id="label-filter"
          value={filters.label || 'all'}
          onChange={handleLabelChange}
          className="w-40"
        >
          <option value="all">All Labels</option>
          {schema?.allowed_labels.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </Select>
      </div>

      {/* Name Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Search by name..."
          value={searchValue}
          onChange={handleSearchChange}
          className="pl-9"
        />
      </div>
    </div>
  );
}
