import React, { useCallback, useRef, useState } from 'react';
import { useUiStore } from '@/stores';
import { cn } from '@/lib/utils';

interface SplitViewProps {
  leftPanel: React.ReactNode;
  rightPanel: React.ReactNode;
  rightCollapsed?: boolean;
  className?: string;
}

export function SplitView({ leftPanel, rightPanel, rightCollapsed = false, className }: SplitViewProps) {
  const { leftPanelWidth, setLeftPanelWidth } = useUiStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging || !containerRef.current) return;

      const container = containerRef.current;
      const containerRect = container.getBoundingClientRect();
      const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100;
      setLeftPanelWidth(newWidth);
    },
    [isDragging, setLeftPanelWidth]
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  React.useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <div
      ref={containerRef}
      className={cn('flex h-full w-full overflow-hidden', className)}
    >
      {/* Left Panel */}
      <div
        className="h-full overflow-hidden transition-all duration-300 ease-in-out"
        style={{ width: rightCollapsed ? '100%' : `${leftPanelWidth}%` }}
      >
        {leftPanel}
      </div>

      {/* Resize Handle — hidden when collapsed */}
      {!rightCollapsed && (
        <div
          className={cn(
            'w-[3px] cursor-col-resize transition-colors',
            'bg-transparent hover:bg-primary/20',
            'shadow-[inset_1px_0_0_0_rgb(0_0_0/0.04)]',
            isDragging && 'bg-primary/30'
          )}
          onMouseDown={handleMouseDown}
        />
      )}

      {/* Right Panel — CSS transition for width */}
      <div
        className={cn(
          'h-full transition-all duration-300 ease-in-out overflow-hidden bg-gray-50/50',
          rightCollapsed ? 'w-0 opacity-0' : 'opacity-100'
        )}
        style={rightCollapsed ? undefined : { width: `${100 - leftPanelWidth}%` }}
      >
        {rightPanel}
      </div>
    </div>
  );
}

export default SplitView;
