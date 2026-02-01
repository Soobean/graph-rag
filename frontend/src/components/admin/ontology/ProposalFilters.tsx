import { useState, useEffect, useCallback } from 'react';
import { Select } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Search } from 'lucide-react';
import { useDebouncedCallback } from '@/hooks/useDebounce';
import type { ProposalListParams } from '@/api/hooks/admin/useOntologyAdmin';

interface ProposalFiltersProps {
  filters: ProposalListParams;
  onFiltersChange: (filters: ProposalListParams) => void;
}

const SEARCH_DEBOUNCE_MS = 300;

export function ProposalFilters({ filters, onFiltersChange }: ProposalFiltersProps) {
  const [searchValue, setSearchValue] = useState(filters.term_search || '');

  // Sync external filter changes to local state
  useEffect(() => {
    setSearchValue(filters.term_search || '');
  }, [filters.term_search]);

  const debouncedSearch = useDebouncedCallback(
    useCallback(
      (value: string) => {
        onFiltersChange({
          ...filters,
          term_search: value || undefined,
          page: 1,
        });
      },
      [filters, onFiltersChange]
    ),
    SEARCH_DEBOUNCE_MS
  );

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFiltersChange({
      ...filters,
      status: e.target.value as ProposalListParams['status'],
      page: 1,
    });
  };

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFiltersChange({
      ...filters,
      proposal_type: e.target.value as ProposalListParams['proposal_type'],
      page: 1,
    });
  };

  const handleSourceChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFiltersChange({
      ...filters,
      source: e.target.value as ProposalListParams['source'],
      page: 1,
    });
  };

  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const [sort_by, sort_order] = e.target.value.split(':') as [
      ProposalListParams['sort_by'],
      ProposalListParams['sort_order'],
    ];
    onFiltersChange({
      ...filters,
      sort_by,
      sort_order,
    });
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchValue(value);
    debouncedSearch(value);
  };

  return (
    <div className="flex flex-wrap items-center gap-4">
      {/* Status Filter */}
      <div className="flex items-center gap-2">
        <label htmlFor="status" className="text-sm font-medium">
          Status:
        </label>
        <Select id="status" value={filters.status || 'pending'} onChange={handleStatusChange} className="w-32">
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="auto_approved">Auto-Approved</option>
          <option value="rejected">Rejected</option>
          <option value="all">All</option>
        </Select>
      </div>

      {/* Type Filter */}
      <div className="flex items-center gap-2">
        <label htmlFor="type" className="text-sm font-medium">
          Type:
        </label>
        <Select id="type" value={filters.proposal_type || 'all'} onChange={handleTypeChange} className="w-36">
          <option value="all">All Types</option>
          <option value="NEW_CONCEPT">New Concept</option>
          <option value="NEW_SYNONYM">New Synonym</option>
          <option value="NEW_RELATION">New Relation</option>
        </Select>
      </div>

      {/* Source Filter */}
      <div className="flex items-center gap-2">
        <label htmlFor="source" className="text-sm font-medium">
          Source:
        </label>
        <Select id="source" value={filters.source || 'all'} onChange={handleSourceChange} className="w-32">
          <option value="all">All Sources</option>
          <option value="chat">Chat</option>
          <option value="background">Background</option>
          <option value="admin">Admin</option>
        </Select>
      </div>

      {/* Sort */}
      <div className="flex items-center gap-2">
        <label htmlFor="sort" className="text-sm font-medium">
          Sort:
        </label>
        <Select
          id="sort"
          value={`${filters.sort_by || 'created_at'}:${filters.sort_order || 'desc'}`}
          onChange={handleSortChange}
          className="w-40"
        >
          <option value="created_at:desc">Newest First</option>
          <option value="created_at:asc">Oldest First</option>
          <option value="frequency:desc">Highest Frequency</option>
          <option value="confidence:desc">Highest Confidence</option>
        </Select>
      </div>

      {/* Search */}
      <div className="relative flex-1 min-w-[200px]">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Search terms..."
          value={searchValue}
          onChange={handleSearchChange}
          className="pl-9"
        />
      </div>
    </div>
  );
}
