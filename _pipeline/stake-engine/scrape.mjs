/**
 * Stake Engine Game Data Scraper
 *
 * Fetches all games and providers from stakeplayercount.com API.
 * Saves as JSON (full data) and CSV (for spreadsheet analysis).
 *
 * Usage: node scrape.mjs
 *
 * API Endpoints (no auth required):
 *   GET /api/games?page=N&limit=24&sort=players
 *   GET /api/providers?page=1&limit=200
 */

import { writeFileSync, mkdirSync, existsSync, readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE_URL = 'https://stakeplayercount.com/api';
const DATE = new Date().toISOString().slice(0, 10);
const OUTPUT_DIR = join(__dirname, 'data');
const HISTORY_DIR = join(__dirname, 'data', 'history');

mkdirSync(OUTPUT_DIR, { recursive: true });
mkdirSync(HISTORY_DIR, { recursive: true });

// --- Fetch helpers ---

async function fetchJSON(url, attempt = 1) {
  try {
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json' },
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    return res.json();
  } catch (err) {
    if (attempt >= 4) throw err;
    const delay = [2000, 8000, 30000][attempt - 1];
    console.log(`  Fetch failed (${err.message}), retry ${attempt}/3 in ${delay / 1000}s...`);
    await new Promise((r) => setTimeout(r, delay));
    return fetchJSON(url, attempt + 1);
  }
}

async function fetchAllGames() {
  console.log('Fetching games...');
  const allGames = [];
  let page = 1;
  const limit = 50; // Max per page

  while (true) {
    const url = `${BASE_URL}/games?page=${page}&limit=${limit}&sort=players`;
    const data = await fetchJSON(url);

    if (!data.games || data.games.length === 0) break;

    allGames.push(...data.games);
    console.log(`  Page ${page}: ${data.games.length} games (total: ${allGames.length})`);

    if (data.games.length < limit) break;
    page++;

    // Be polite - small delay between requests
    await new Promise((r) => setTimeout(r, 300));
  }

  return allGames;
}

async function fetchAllProviders() {
  console.log('Fetching providers...');
  // API clamps limit to 100 — paginate like fetchAllGames
  const allProviders = [];
  let page = 1;
  while (true) {
    const data = await fetchJSON(`${BASE_URL}/providers?page=${page}&limit=100`);
    const batch = data.providers || [];
    if (batch.length === 0) break;

    allProviders.push(...batch);
    console.log(`  Page ${page}: ${batch.length} providers (total: ${allProviders.length})`);

    if (data.pagination ? !data.pagination.hasMore : batch.length < 100) break;
    page++;

    await new Promise((r) => setTimeout(r, 300));
  }
  return allProviders;
}

// --- CSV helpers ---

function escapeCsv(val) {
  if (val == null) return '';
  const str = String(val);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function gamesToCsv(games) {
  const headers = [
    'rank', 'name', 'provider', 'totalPlayers', 'comPlayers', 'usPlayers',
    'turnover', 'turnoverUSD', 'betCount', 'activeChallenges',
    'avgBetSize', 'playersPerChallenge', 'slug',
  ];

  const rows = games.map((g, i) => {
    const turnoverUSD = g.turnover / 100; // Assuming cents
    const avgBet = g.betCount > 0 ? turnoverUSD / g.betCount : 0;
    return [
      i + 1,
      g.name,
      g.provider,
      g.totalPlayers,
      g.comPlayers,
      g.usPlayers,
      g.turnover,
      turnoverUSD.toFixed(2),
      g.betCount,
      g.activeChallenges,
      avgBet.toFixed(2),
      g.activeChallenges > 0 ? (g.totalPlayers / g.activeChallenges).toFixed(1) : 'N/A',
      g.slug,
    ].map(escapeCsv).join(',');
  });

  return [headers.join(','), ...rows].join('\n');
}

function providersToCsv(providers) {
  const headers = [
    'rank', 'name', 'totalPlayers', 'gameCount', 'activeChallenges',
    'playersPerGame', 'slug',
  ];

  const rows = providers.map((p, i) => [
    i + 1,
    p.name,
    p.totalPlayers,
    p.gameCount,
    p.activeChallenges,
    p.gameCount > 0 ? (p.totalPlayers / p.gameCount).toFixed(1) : 0,
    p.slug,
  ].map(escapeCsv).join(','));

  return [headers.join(','), ...rows].join('\n');
}

// --- Main ---

async function main() {
  console.log(`\nStake Engine Scraper - ${DATE}`);
  console.log('='.repeat(50));

  const games = await fetchAllGames();
  const providers = await fetchAllProviders();

  // Enrich games with provider display name
  const providerMap = Object.fromEntries(providers.map((p) => [p.slug, p.name]));
  for (const g of games) {
    g.providerName = providerMap[g.provider] || g.provider;
  }

  // Summary stats
  const totalPlayers = providers.reduce((sum, p) => sum + p.totalPlayers, 0);
  const totalTurnover = games.reduce((sum, g) => sum + (g.turnover || 0), 0);
  const totalBets = games.reduce((sum, g) => sum + (g.betCount || 0), 0);

  const summary = {
    date: DATE,
    timestamp: new Date().toISOString(),
    totalGames: games.length,
    totalProviders: providers.length,
    totalLivePlayers: totalPlayers,
    totalTurnover: totalTurnover,
    totalTurnoverUSD: (totalTurnover / 100).toFixed(2),
    totalBets: totalBets,
  };

  console.log(`\n--- Summary ---`);
  console.log(`Games: ${summary.totalGames}`);
  console.log(`Providers: ${summary.totalProviders}`);
  console.log(`Live players: ${summary.totalLivePlayers}`);
  console.log(`Total turnover: $${(totalTurnover / 100_000_000).toFixed(1)}M`);
  console.log(`Total bets: ${(totalBets / 1_000_000).toFixed(1)}M`);

  // Save full JSON (latest)
  const fullData = { summary, games, providers };
  const jsonFile = join(OUTPUT_DIR, 'stake_engine_latest.json');
  writeFileSync(jsonFile, JSON.stringify(fullData, null, 2));
  console.log(`\nSaved: ${jsonFile}`);

  // Save CSVs (latest)
  const gamesCsvFile = join(OUTPUT_DIR, 'stake_engine_games.csv');
  writeFileSync(gamesCsvFile, gamesToCsv(games));
  console.log(`Saved: ${gamesCsvFile}`);

  const providersCsvFile = join(OUTPUT_DIR, 'stake_engine_providers.csv');
  writeFileSync(providersCsvFile, providersToCsv(providers));
  console.log(`Saved: ${providersCsvFile}`);

  // Save historical snapshot
  const historyFile = join(HISTORY_DIR, `snapshot_${DATE}.json`);
  writeFileSync(historyFile, JSON.stringify(fullData, null, 2));
  console.log(`Saved: ${historyFile}`);

  // Append to daily summary log
  const logFile = join(OUTPUT_DIR, 'daily_summary.jsonl');
  const logLine = JSON.stringify(summary) + '\n';
  const existingLog = existsSync(logFile) ? readFileSync(logFile, 'utf-8') : '';
  writeFileSync(logFile, existingLog + logLine);
  console.log(`Appended to: ${logFile}`);

  console.log('\nDone!');
}

main().catch((err) => {
  console.error('Scraper failed:', err.message);
  process.exit(1);
});
