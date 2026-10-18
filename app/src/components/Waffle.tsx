// 100 dots; `fill` of them highlighted (.5 = a half dot).
export function Waffle({ fill, className }: { fill: number; className?: string }) {
  const full = Math.floor(fill);
  const half = fill - full >= 0.5;
  return (
    <div className={className ? `waffle ${className}` : 'waffle'} role="img" aria-label={`${fill} in 100`}>
      {Array.from({ length: 100 }, (_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: a fixed grid of identical dots
        <span key={i} className={i < full ? 'on' : i === full && half ? 'half' : undefined} />
      ))}
    </div>
  );
}
