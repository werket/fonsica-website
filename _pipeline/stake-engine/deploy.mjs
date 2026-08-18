#!/usr/bin/env node
/**
 * Stake Engine Dashboard - Daily Deploy Pipeline
 *
 * 1. Fetches latest data from stakeplayercount.com API
 * 2. Categorizes all games
 * 3. Regenerates dashboard HTML with live data
 * 4. Git commit + push → GitHub Pages auto-deploys
 *
 * Usage: node deploy.mjs
 */

import { readFileSync, writeFileSync, mkdirSync, appendFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const dataDir = join(__dirname, 'data');
const repoRoot = join(__dirname, '..', '..');
const dashboardFile = join(repoRoot, 'insights', 'stake-engine', 'index.html');

const BASE_URL = 'https://stakeplayercount.com/api';
const today = new Date().toISOString().split('T')[0];
const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const now = new Date();
const dateFormatted = `${months[now.getMonth()]} ${now.getDate()}, ${now.getFullYear()}`;

console.log(`\nStake Engine Dashboard Deploy - ${today}`);
console.log('='.repeat(50));

// ============================================================
// STEP 1: FETCH DATA
// ============================================================
console.log('\n[1/5] Fetching data from API...');

async function fetchJSON(url, attempt = 1) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(15000) });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    return res.json();
  } catch (err) {
    if (attempt >= 4) throw err;
    const delay = [2000, 8000, 30000][attempt - 1];
    console.log(`  Fetch failed (${err.message}), retry ${attempt}/3 in ${delay / 1000}s...`);
    await new Promise(r => setTimeout(r, delay));
    return fetchJSON(url, attempt + 1);
  }
}

async function fetchAllGames() {
  let allGames = [];
  let page = 1;
  while (true) {
    const data = await fetchJSON(`${BASE_URL}/games?page=${page}&limit=50&sort=players`);
    allGames = allGames.concat(data.games || []);
    if (!data.pagination?.hasMore) break;
    page++;
    await new Promise(r => setTimeout(r, 200));
  }
  return allGames;
}

async function fetchAllProviders() {
  // API clamps limit to 100 — paginate
  let all = [];
  let page = 1;
  while (true) {
    const data = await fetchJSON(`${BASE_URL}/providers?page=${page}&limit=100`);
    const batch = data.providers || [];
    if (batch.length === 0) break;
    all = all.concat(batch);
    if (data.pagination ? !data.pagination.hasMore : batch.length < 100) break;
    page++;
    await new Promise(r => setTimeout(r, 200));
  }
  return all;
}

const [games, providers] = await Promise.all([
  fetchAllGames(),
  fetchAllProviders(),
]);
console.log(`  Games: ${games.length}, Providers: ${providers.length}`);

// Add providerName to games
const providerMap = {};
providers.forEach(p => { providerMap[p.slug || p.provider] = p.name; });
games.forEach(g => { g.providerName = providerMap[g.provider] || g.provider; });

const totalPlayers = games.reduce((s, g) => s + g.totalPlayers, 0);
const totalBets = games.reduce((s, g) => s + (g.betCount || 0), 0);
const comPlayers = games.reduce((s, g) => s + (g.comPlayers || 0), 0);
const usPlayers = games.reduce((s, g) => s + (g.usPlayers || 0), 0);
const comPct = ((comPlayers / totalPlayers) * 100).toFixed(1);
const usPct = ((usPlayers / totalPlayers) * 100).toFixed(1);

console.log(`  Live players: ${totalPlayers.toLocaleString()}`);

// Save snapshot
mkdirSync(join(dataDir, 'history'), { recursive: true });
const snapshot = { summary: { date: today, timestamp: new Date().toISOString(), totalGames: games.length, totalProviders: providers.length, totalLivePlayers: totalPlayers }, games, providers };
writeFileSync(join(dataDir, 'stake_engine_latest.json'), JSON.stringify(snapshot, null, 2));
writeFileSync(join(dataDir, 'history', `snapshot_${today}.json`), JSON.stringify(snapshot, null, 2));
appendFileSync(join(dataDir, 'daily_summary.jsonl'), JSON.stringify({ date: today, timestamp: new Date().toISOString(), totalGames: games.length, totalProviders: providers.length, totalLivePlayers: totalPlayers, totalBets }) + '\n');

// ============================================================
// STEP 2: CATEGORIZE GAMES
// ============================================================
console.log('[2/5] Categorizing games...');

const arcadeGames = new Set([
  'Angry Balls', 'Elf Balls', "Dr Undeds Boo Balls", "Beelzebub's Balls", " Beelzebub's Balls", "BEELZEBUB'S BALLS!",
  'Drop The Boss', 'Drop The Llama',
  'Beer Pong', 'Flip Cup',
  'Fruit Cutter', 'Fruit Samurai',
  'Flappy Fortune', 'Fly Bird',
  'Jump', 'Jump Guy', 'Sketch Jump', 'Space Jump',
  'Chicken Run', 'Line Runner', 'Stumble Guy', 'Subway Spraydown',
  'Penguins Can Fly',
  'Pinball Peak', 'Pinball Street',
  'Duck Shots', 'Duck Shots Christmas Edition', 'Duckshot Deadwood',
  'TARGETS', 'Quickshot', 'SPINSHOT',
  'Stuntman Dan', 'Stuntman Santa',
  "Slingin' Pumpkins", 'Smash The Pumpkin', 'Smash & Cash', 'Polar Smash',
  'Maze Quest', 'The Maze',
  'Defuse It!', 'Russian Roulette',
  'Jetpack Treasure Hunter', 'Jetpack Wars',
  'Kill The Bill', 'BLOCK NINJA',
  'Fumble Tumble', 'TUMBLER',
  'Cart Commander', 'Craft Hero',
  'Biolab Mayhem', 'Tiny Racer',
]);

function categorizeGame(name) {
  if (arcadeGames.has(name)) return 'Arcade / Other';
  if (/\bdeath dice\b/i.test(name)) return 'Dice';
  if (/\bdomino\b/i.test(name)) return 'Dice';
  if (/\bkeno\b/i.test(name)) return 'Keno';
  if (/\bplinko\b/i.test(name)) return 'Plinko';
  if (/\bpachinko\b/i.test(name)) return 'Pachinko';
  if (/\bdice\b/i.test(name)) return 'Dice';
  return 'Slots';
}

const categorizedGames = games.map(g => ({ ...g, category: categorizeGame(g.name) }));

const catSet = new Set(categorizedGames.map(g => g.category));
console.log(`  Categories: ${catSet.size}`);

// ============================================================
// STEP 3: BUILD DASHBOARD HTML
// ============================================================
console.log('[3/5] Building dashboard...');

// Read the live dashboard file (single source of truth)
const template = readFileSync(dashboardFile, 'utf8');

// --- Replace date ---
let html = template.replace(
  /Live data &middot; [A-Z][a-z]+ \d+, \d{4}/,
  `Live data &middot; ${dateFormatted}`
);

// --- Replace hero stats ---
html = html.replace(
  /data-count="\d+"(>0<\/div>\s*<div class="hero-stat-label">Games Tracked)/,
  `data-count="${games.length}"$1`
);
html = html.replace(
  /data-count="\d+"(>0<\/div>\s*<div class="hero-stat-label">Live Players)/,
  `data-count="${totalPlayers}"$1`
);
html = html.replace(
  /data-count="\d+"(>0<\/div>\s*<div class="hero-stat-label">Providers)/,
  `data-count="${providers.length}"$1`
);
html = html.replace(
  /data-count="\d+"(>0<\/div>\s*<div class="hero-stat-label">Million Bets)/,
  `data-count="${Math.round(totalBets / 1e6)}"$1`
);

// --- Replace hero subtitle ---
html = html.replace(
  /Real-time performance analytics across \d+ games and \d+ providers/,
  `Real-time performance analytics across ${games.length} games and ${providers.length} providers`
);

// --- Replace allGames array with ALL games + category field ---
const allGamesJS = categorizedGames.map(g => {
  const n = g.name.replace(/"/g, '\\"');
  const p = g.providerName.replace(/"/g, '\\"');
  const cat = g.category.replace(/"/g, '\\"');
  return `{n:"${n}",s:"${g.slug}",t:"${g.thumbnail}",p:"${p}",ps:"${g.provider}",tp:${g.totalPlayers},com:${g.comPlayers||0},us:${g.usPlayers||0},bets:${g.betCount||0},ch:${g.activeChallenges||0},cat:"${cat}"}`;
}).join(',\n');

html = html.replace(
  /const allGames = \[[\s\S]*?\];/,
  `const allGames = [\n${allGamesJS}\n];`
);

// --- Replace market split static labels ---
html = html.replace(/split-bar com"[^>]*>[^<]*</g, `split-bar com" id="splitCom">${comPct}%<`);
html = html.replace(/split-bar us"[^>]*>[^<]*</g, `split-bar us" id="splitUs">${usPct}%<`);
html = html.replace(
  /stake\.com &middot; [\d,]+ players/,
  `stake.com &middot; ${comPlayers.toLocaleString()} players`
);
html = html.replace(
  /stake\.us &middot; [\d,]+ players/,
  `stake.us &middot; ${usPlayers.toLocaleString()} players`
);

// --- Replace footer date ---
html = html.replace(
  /Snapshot: [A-Z][a-z]+ \d+, \d{4} \d{2}:\d{2} UTC/,
  `Snapshot: ${dateFormatted} ${now.getUTCHours().toString().padStart(2,'0')}:${now.getUTCMinutes().toString().padStart(2,'0')} UTC`
);
html = html.replace(
  /\d+ games &middot; \d+ providers &middot; Updated daily/,
  `${games.length} games &middot; ${providers.length} providers &middot; Updated daily`
);

// ============================================================
// STEP 4: WRITE DASHBOARD
// ============================================================
console.log('[4/5] Writing dashboard...');

// Write back to the single source of truth
writeFileSync(dashboardFile, html);

console.log(`  Dashboard saved (${(html.length / 1024).toFixed(0)} KB)`);

// ============================================================
// STEP 5: GIT PUSH
// ============================================================
console.log('[5/5] Pushing to GitHub...');

try {
  execSync(`cd "${repoRoot}" && git add insights/stake-engine/index.html && git diff --cached --quiet`, { stdio: 'pipe' });
  console.log('  No changes to push (data unchanged).');
} catch {
  // There are changes to commit
  const msg = `Update Stake Engine dashboard - ${today}\n\n${games.length} games, ${totalPlayers.toLocaleString()} live players, ${providers.length} providers\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>`;
  execSync(`cd "${repoRoot}" && git add insights/stake-engine/index.html && git commit -m "${msg.replace(/"/g, '\\"')}"`, { stdio: 'pipe' });
  execSync(`cd "${repoRoot}" && git push origin main`, { stdio: 'pipe' });
  console.log('  Pushed to GitHub Pages!');
}

console.log(`\nDone! Live at: https://fonsica.se/insights/stake-engine/\n`);
