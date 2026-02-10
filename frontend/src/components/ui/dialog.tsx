import * as React from 'react';
import { cn } from '@/lib/utils';
import { X } from 'lucide-react';

interface DialogContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

function Dialog({ open = false, onOpenChange, children }: DialogProps) {
  const [internalOpen, setInternalOpen] = React.useState(open);

  const isControlled = onOpenChange !== undefined;
  const isOpen = isControlled ? open : internalOpen;
  const setIsOpen = isControlled ? onOpenChange : setInternalOpen;

  return <DialogContext.Provider value={{ open: isOpen, onOpenChange: setIsOpen }}>{children}</DialogContext.Provider>;
}

function useDialog() {
  const context = React.useContext(DialogContext);
  if (!context) {
    throw new Error('useDialog must be used within a Dialog');
  }
  return context;
}

interface DialogTriggerProps {
  children: React.ReactNode;
  asChild?: boolean;
}

function DialogTrigger({ children, asChild }: DialogTriggerProps) {
  const { onOpenChange } = useDialog();

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<{ onClick?: () => void }>, {
      onClick: () => onOpenChange(true),
    });
  }

  return (
    <button type="button" onClick={() => onOpenChange(true)}>
      {children}
    </button>
  );
}

type DialogContentProps = React.HTMLAttributes<HTMLDivElement>;

function DialogContent({ className, children, ...props }: DialogContentProps) {
  const { open, onOpenChange } = useDialog();
  const contentRef = React.useRef<HTMLDivElement>(null);
  const previousActiveElement = React.useRef<HTMLElement | null>(null);

  // Ref로 최신 onOpenChange를 참조 — useEffect deps에서 제거하여
  // 부모 리렌더 시 불필요한 effect 재실행(+ 포커스 강탈) 방지
  const onOpenChangeRef = React.useRef(onOpenChange);
  React.useEffect(() => {
    onOpenChangeRef.current = onOpenChange;
  });

  // ESC 키로 닫기 및 포커스 관리
  React.useEffect(() => {
    if (!open) return;

    // 열릴 때 현재 포커스 저장
    previousActiveElement.current = document.activeElement as HTMLElement;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onOpenChangeRef.current(false);
      }
    };

    // 포커스 트랩
    const handleTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || !contentRef.current) return;

      const focusableElements = contentRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey && document.activeElement === firstElement) {
        e.preventDefault();
        lastElement?.focus();
      } else if (!e.shiftKey && document.activeElement === lastElement) {
        e.preventDefault();
        firstElement?.focus();
      }
    };

    document.addEventListener('keydown', handleEscape);
    document.addEventListener('keydown', handleTab);

    // 다이얼로그 열릴 때 포커스 이동
    requestAnimationFrame(() => {
      contentRef.current?.focus();
    });

    // body 스크롤 방지
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.removeEventListener('keydown', handleTab);
      document.body.style.overflow = '';
      // 닫힐 때 이전 포커스 복원
      previousActiveElement.current?.focus();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50"
        onClick={() => onOpenChange(false)}
        aria-hidden="true"
      />

      {/* Content */}
      <div
        ref={contentRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className={cn(
          'relative z-50 grid w-full max-w-lg gap-4 border bg-background p-6 shadow-lg sm:rounded-lg focus:outline-none',
          className
        )}
        onClick={(e) => e.stopPropagation()}
        {...props}
      >
        {children}
        <button
          type="button"
          aria-label="Close dialog"
          className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
          onClick={() => onOpenChange(false)}
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </button>
      </div>
    </div>
  );
}

function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)} {...props} />;
}

function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2', className)} {...props} />;
}

function DialogTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn('text-lg font-semibold leading-none tracking-tight', className)} {...props} />;
}

function DialogDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn('text-sm text-muted-foreground', className)} {...props} />;
}

export { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription };
