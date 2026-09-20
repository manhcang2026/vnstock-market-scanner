export function mergeWatchlistWithMetadata(watchlistRows, metadataRows) {
  const metadataBySymbol = new Map(metadataRows.map((row) => [String(row.symbol || '').trim().toUpperCase(), row]))
  return watchlistRows.map((item) => {
    const symbol = String(item.symbol || '').trim().toUpperCase()
    const metadata = metadataBySymbol.get(symbol)
    return {
      symbol,
      added_at: item.added_at,
      add_source: item.add_source,
      display_name: metadata?.display_name || null,
      company_name: metadata?.company_name || null,
      exchange: metadata?.exchange || null,
    }
  })
}
