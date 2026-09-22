import { expect, it } from 'vitest';
import { shouldSend } from '../../src/components/composer-input';

it('Enter sends, Shift+Enter and Chinese composition do not', () => {
  expect(shouldSend({ key: 'Enter', shiftKey: false, isComposing: false, keyCode: 13 })).toBe(true);
  expect(shouldSend({ key: 'Enter', shiftKey: true, isComposing: false, keyCode: 13 })).toBe(false);
  expect(shouldSend({ key: 'Enter', shiftKey: false, isComposing: true, keyCode: 13 })).toBe(false);
  expect(shouldSend({ key: 'Enter', shiftKey: false, isComposing: false, keyCode: 229 })).toBe(false);
});
