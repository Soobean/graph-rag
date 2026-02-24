import React, { useState, useCallback } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import SEARCH from "@/assets/svg/SEARCH.svg";
import { useChatStore } from "@/stores";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading?: boolean;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}

export function ChatInput({
  onSend,
  isLoading = false,
  disabled = false,
  placeholder = "질문을 입력하세요...",
  className,
}: ChatInputProps) {
  const { getCurrentMessages } = useChatStore();
  const messages = getCurrentMessages();

  const [input, setInput] = useState("");

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = input.trim();
      if (trimmed && !isLoading && !disabled) {
        onSend(trimmed);
        setInput("");
      }
    },
    [input, isLoading, disabled, onSend],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.nativeEvent.isComposing) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit(e);
      }
    },
    [handleSubmit],
  );

  const isLanding = messages.length === 0;

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        `relative flex items-center gap-2 p-4 ${!isLanding && "bg-background-light-blue"}`,
        className,
      )}
    >
      <img src={SEARCH} alt="검색 아이콘" className="absolute left-8" />
      <Input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={isLanding ? placeholder : "답글"}
        disabled={isLoading || disabled}
        className="flex-1 h-[56px] pl-11 rounded-[14px] shadow-[0_2px_16px_0_rgba(0,0,0,0.08)]"
      />
      <Button
        type="submit"
        variant="default"
        size="icon"
        disabled={!input.trim() || isLoading || disabled}
        className={cn("absolute right-6")}
      >
        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Send className="h-4 w-4" />
        )}
      </Button>
    </form>
  );
}

export default ChatInput;
