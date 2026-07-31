export class EpochLatchMap<TKey, TValue> {
  private readonly entries = new Map<
    TKey,
    { value: TValue; epoch: number }
  >();
  private nextEpoch = 1;

  get size(): number {
    return this.entries.size;
  }

  has(key: TKey): boolean {
    return this.entries.has(key);
  }

  value(key: TKey): TValue | null {
    return this.entries.get(key)?.value ?? null;
  }

  epoch(key: TKey): number | null {
    return this.entries.get(key)?.epoch ?? null;
  }

  mark(key: TKey, value: TValue): number {
    const epoch = this.nextEpoch++;
    this.entries.set(key, { value, epoch });
    return epoch;
  }

  clear(key: TKey, expectedEpoch?: number): boolean {
    if (
      expectedEpoch !== undefined &&
      this.entries.get(key)?.epoch !== expectedEpoch
    ) {
      return false;
    }
    return this.entries.delete(key);
  }
}
