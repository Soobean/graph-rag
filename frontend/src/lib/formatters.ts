/**
 * Shared formatting utilities for Korean Won currency values.
 * Extracted from ProjectStaffing.tsx for reuse across components.
 */

export function formatKRW(amount: number): string {
  if (Math.abs(amount) >= 1_0000_0000) {
    return `${(amount / 1_0000_0000).toFixed(1)}억원`;
  }
  if (Math.abs(amount) >= 1_0000) {
    return `${Math.round(amount / 1_0000).toLocaleString('ko-KR')}만원`;
  }
  return `${amount.toLocaleString('ko-KR')}원`;
}

export function formatRate(rate: number): string {
  return `₩${rate.toLocaleString('ko-KR')}`;
}
