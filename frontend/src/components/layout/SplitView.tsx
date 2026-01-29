import React, { useCallback, useRef, useState } from 'react';
import { useUiStore } from '@/stores';
import { cn } from '@/lib/utils';

interface SplitViewProps {
  leftPanel: React.ReactNode;
  rightPanel: React.ReactNode;
  className?: string;
}

export function SplitView({ leftPanel, rightPanel, className }: SplitViewProps) {
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
        className="h-full overflow-hidden border-r border-border"
        style={{ width: `${leftPanelWidth}%` }}
      >
        {leftPanel}
      </div>

      {/* Resize Handle */}
      <div
        className={cn(
          'w-1 cursor-col-resize bg-border hover:bg-primary/50 transition-colors',
          isDragging && 'bg-primary'
        )}
        onMouseDown={handleMouseDown}
      />

      {/* Right Panel */}
      <div
        className="h-full overflow-hidden"
        style={{ width: `${100 - leftPanelWidth}%` }}
      >
        {rightPanel}
      </div>
    </div>
  );
}

export default SplitView;
