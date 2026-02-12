import { describe, it, expect } from 'vitest';
import { formatKRW, formatRate } from './formatters';

describe('formatKRW', () => {
  describe('Happy path - normal values', () => {
    it('formats amounts >= 1억 in 억원', () => {
      expect(formatKRW(1_0000_0000)).toBe('1.0억원');
      expect(formatKRW(2_5000_0000)).toBe('2.5억원');
      expect(formatKRW(10_0000_0000)).toBe('10.0억원');
    });

    it('formats amounts >= 1만 in 만원', () => {
      expect(formatKRW(1_0000)).toBe('1만원');
      expect(formatKRW(5_0000)).toBe('5만원');
      expect(formatKRW(12_3456)).toBe('12만원'); // Rounds down
      expect(formatKRW(99_9999)).toBe('100만원'); // Rounds up
    });

    it('formats amounts < 1만 in 원', () => {
      expect(formatKRW(1000)).toBe('1,000원');
      expect(formatKRW(5000)).toBe('5,000원');
      expect(formatKRW(9999)).toBe('9,999원');
    });
  });

  describe('Edge case - zero', () => {
    it('formats zero as 0원', () => {
      expect(formatKRW(0)).toBe('0원');
    });
  });

  describe('Edge case - negative values', () => {
    it('formats negative values with correct magnitude', () => {
      expect(formatKRW(-1_0000_0000)).toBe('-1.0억원');
      expect(formatKRW(-5_0000)).toBe('-5만원');
      expect(formatKRW(-1000)).toBe('-1,000원');
    });
  });

  describe('Edge case - boundary values', () => {
    it('formats boundary at 1억 (99,999,999 vs 100,000,000)', () => {
      expect(formatKRW(9999_9999)).toBe('10,000만원'); // Just below 1억, rounds to 10,000만원
      expect(formatKRW(1_0000_0000)).toBe('1.0억원'); // Exactly 1억
    });

    it('formats boundary at 1만 (9,999 vs 10,000)', () => {
      expect(formatKRW(9999)).toBe('9,999원'); // Just below 1만
      expect(formatKRW(1_0000)).toBe('1만원'); // Exactly 1만
    });
  });

  describe('Edge case - decimal precision', () => {
    it('shows one decimal place for 억원', () => {
      expect(formatKRW(1_5000_0000)).toBe('1.5억원');
      expect(formatKRW(1_2345_6789)).toBe('1.2억원'); // Rounds down
      expect(formatKRW(1_9876_5432)).toBe('2.0억원'); // Rounds up
    });

    it('rounds to nearest integer for 만원', () => {
      expect(formatKRW(1_4999)).toBe('1만원'); // 1.4999만원 → 1만원
      expect(formatKRW(1_5000)).toBe('2만원'); // 1.5만원 → 2만원
    });
  });

  describe('Edge case - locale formatting', () => {
    it('uses Korean locale for number formatting', () => {
      expect(formatKRW(1234)).toBe('1,234원'); // Comma as thousand separator
      expect(formatKRW(123_4567)).toBe('123만원');
    });
  });
});

describe('formatRate', () => {
  describe('Happy path - normal values', () => {
    it('formats rates with ₩ prefix and thousand separators', () => {
      expect(formatRate(50000)).toBe('₩50,000');
      expect(formatRate(120000)).toBe('₩120,000');
      expect(formatRate(1000000)).toBe('₩1,000,000');
    });
  });

  describe('Edge case - zero', () => {
    it('formats zero as ₩0', () => {
      expect(formatRate(0)).toBe('₩0');
    });
  });

  describe('Edge case - negative values', () => {
    it('formats negative rates', () => {
      expect(formatRate(-50000)).toBe('₩-50,000');
    });
  });

  describe('Edge case - small values', () => {
    it('formats single digit values', () => {
      expect(formatRate(1)).toBe('₩1');
      expect(formatRate(10)).toBe('₩10');
      expect(formatRate(100)).toBe('₩100');
    });
  });
});
