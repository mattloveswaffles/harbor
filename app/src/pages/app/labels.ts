import type { IconName } from '../../components/Icon.tsx';
import type { Move, Plan } from '../../lib/types.ts';

const PLAN_STATUS: Partial<Record<Plan['status'], [label: string, tone: 'ok' | 'warn' | '']>> = {
  awaiting_approval: ['Needs approval', 'warn'],
  approved: ['Approved', 'ok'],
  running: ['Running', 'ok'],
  complete: ['Complete', 'ok'],
  restoring: ['Restoring', ''],
  restored: ['Restored', 'ok'],
  cancelled: ['Cancelled', ''],
  expired: ['Expired', ''],
};
export const planStatus = (plan: Plan) => PLAN_STATUS[plan.status] ?? [plan.status, ''];

export const MOVE_STATUS: Record<Move['status'], string> = {
  proposed: 'Proposed',
  scheduled: 'Scheduled',
  executing: 'Running',
  pending_settlement: 'Settling',
  done: 'Done',
  cancelled: 'Cancelled',
  failed: 'Failed',
};

export function moveLabel(m: Move): [IconName, string] {
  const symbol = m.symbol ?? 'ETF';
  switch (m.kind) {
    case 'transfer':
      return ['savings', 'Savings → checking'];
    case 'sell_etf':
      return ['chart', `Sell ${symbol}`];
    case 'withdraw_cash':
      return ['money', 'Withdraw cash'];
    case 'defer_bill':
      return ['calendar', 'Delay a bill'];
    case 'log_purchase':
      return ['wallet', 'Log spending'];
    case 'restore_transfer':
      return ['undo', 'Back to savings'];
    case 'rebuy_etf':
      return ['chart', `Buy back ${symbol}`];
  }
}

/** Events worth a toast when they arrive live. */
export const TOAST_EVENTS = new Set([
  'risk_changed',
  'plan_created',
  'plan_approved',
  'move_done',
  'move_failed',
  'plan_complete',
]);

/** The top bar's "Ask Harbor anything" leaves its question here for the chat to send. */
export const ASK_KEY = 'harbor.ask';
