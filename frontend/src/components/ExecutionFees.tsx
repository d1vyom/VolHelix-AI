import type { ExecutionAccounting } from '@/lib/types';

/** Native fee amounts only; no unsupported currency conversion or net-PnL claim. */
export function ExecutionFees({ record }: { record: ExecutionAccounting }) {
  const amounts = (fees: Record<string, number> | undefined) =>
    Object.entries(fees || {}).map(([asset, amount]) => `${amount} ${asset}`).join(' · ') || 'No reported amounts';
  const complete = record.fees_known === true && record.exit_fees_known === true;
  return <div className="execution-fees text-[11px] font-normal text-[#b5b7c0] space-y-1">
    <div>Entry fees: {amounts(record.entry_fees)}</div>
    <div>Exit fees: {amounts(record.exit_fees)}</div>
    <div className={complete ? '' : 'text-[#f7a600]'}>{complete ? 'Fee coverage complete' : 'Fee coverage incomplete / unknown'}</div>
    {record.dust_qty != null && record.dust_qty > 0 && <div className="text-[#f7a600]">Dust: {record.dust_qty}{record.base_asset ? ` ${record.base_asset}` : ''} · {record.dust_reason || 'Residual holding retained'}</div>}
  </div>;
}
