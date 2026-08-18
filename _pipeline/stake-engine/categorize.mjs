import { readFileSync, writeFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const dataDir = join(__dirname, 'data');

const data = JSON.parse(readFileSync(join(dataDir, 'stake_engine_latest.json'), 'utf8'));

// ============================================================
// CATEGORY DEFINITIONS
// ~95% of Stake Engine games are slots. A handful of genuinely
// distinct formats exist: Keno, Plinko, Pachinko, Dice, Mines.
// There's also a set of clearly arcade/interactive games
// (physics, runners, pinball, shooting galleries) that are
// NOT slots — these are manually curated.
// ============================================================

// Verified arcade/interactive games — NOT slots.
// These are physics games, runners, shooting galleries, etc.
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
  // Arcade / interactive games (manually verified)
  if (arcadeGames.has(name)) return 'Arcade / Other';

  // Edge cases
  if (/\bdeath dice\b/i.test(name)) return 'Dice';
  if (/\bdomino\b/i.test(name)) return 'Dice';

  // Genuinely distinct formats
  if (/\bkeno\b/i.test(name)) return 'Keno';
  if (/\bplinko\b/i.test(name)) return 'Plinko';
  if (/\bpachinko\b/i.test(name)) return 'Pachinko';
  if (/\bdice\b/i.test(name)) return 'Dice';

  // Everything else is a slot
  return 'Slots';
}

// ============================================================
// PROCESS ALL GAMES
// ============================================================

const categorizedGames = data.games.map(game => ({
  ...game,
  category: categorizeGame(game.name),
}));

// ============================================================
// AGGREGATE BY CATEGORY
// ============================================================

const categoryStats = {};
for (const game of categorizedGames) {
  if (!categoryStats[game.category]) {
    categoryStats[game.category] = {
      name: game.category,
      gameCount: 0,
      totalPlayers: 0,
      totalBets: 0,
      totalChallenges: 0,
      gamesWithPlayers: 0,
      topGame: null,
      topPlayers: 0,
      games: [],
    };
  }
  const cat = categoryStats[game.category];
  cat.gameCount++;
  cat.totalPlayers += game.totalPlayers;
  cat.totalBets += (game.betCount || 0);
  cat.totalChallenges += (game.activeChallenges || 0);
  if (game.totalPlayers > 0) cat.gamesWithPlayers++;
  if (game.totalPlayers > cat.topPlayers) {
    cat.topPlayers = game.totalPlayers;
    cat.topGame = game.name;
  }
  cat.games.push({ name: game.name, players: game.totalPlayers, bets: game.betCount || 0 });
}

// Calculate derived metrics
const categoryArray = Object.values(categoryStats).map(cat => ({
  ...cat,
  playersPerGame: +(cat.totalPlayers / cat.gameCount).toFixed(1),
  successRate: +((cat.gamesWithPlayers / cat.gameCount) * 100).toFixed(1),
  avgBetsPerGame: Math.round(cat.totalBets / cat.gameCount),
}));

// Sort by total players
categoryArray.sort((a, b) => b.totalPlayers - a.totalPlayers);

// ============================================================
// OUTPUT RESULTS
// ============================================================

console.log('\n=== GAME FORMAT PERFORMANCE ===\n');
console.log('Format'.padEnd(14), 'Games'.padStart(6), 'Players'.padStart(8), 'Pl/Game'.padStart(8), 'Success%'.padStart(9), 'TotalBets'.padStart(14), 'Top Game');
console.log('-'.repeat(90));

for (const cat of categoryArray) {
  console.log(
    cat.name.padEnd(14),
    String(cat.gameCount).padStart(6),
    String(cat.totalPlayers).padStart(8),
    String(cat.playersPerGame).padStart(8),
    (cat.successRate + '%').padStart(9),
    String(cat.totalBets.toLocaleString()).padStart(14),
    cat.topGame
  );
}

// Summary stats
console.log('\n=== EFFICIENCY RANKING (Players per Game) ===\n');
const effRanking = categoryArray.sort((a, b) => b.playersPerGame - a.playersPerGame);
effRanking.forEach((cat, i) => {
  console.log(`${i + 1}. ${cat.name}: ${cat.playersPerGame} players/game (${cat.gameCount} games, ${cat.totalPlayers} total players)`);
});

console.log('\n=== SUCCESS RATE (% of games with active players) ===\n');
const successRanking = categoryArray.sort((a, b) => b.successRate - a.successRate);
successRanking.forEach((cat, i) => {
  console.log(`${i + 1}. ${cat.name}: ${cat.successRate}% (${cat.gamesWithPlayers}/${cat.gameCount} games have players)`);
});

// Save categorized data
const output = {
  date: data.summary.date,
  totalGames: categorizedGames.length,
  categories: categoryArray.map(({ games, ...rest }) => rest),
  categoryDetail: categoryArray.map(cat => ({
    name: cat.name,
    games: cat.games.sort((a, b) => b.players - a.players),
  })),
  gameCategories: categorizedGames.map(g => ({ name: g.name, slug: g.slug, category: g.category, totalPlayers: g.totalPlayers, betCount: g.betCount })),
};

writeFileSync(join(dataDir, 'stake_engine_categories.json'), JSON.stringify(output, null, 2));
console.log('\n✓ Saved to stake_engine_categories.json');

// CSV export
const csvLines = ['name,slug,category,totalPlayers,betCount,activeChallenges,provider'];
for (const g of categorizedGames) {
  csvLines.push(`"${g.name}","${g.slug}","${g.category}",${g.totalPlayers},${g.betCount || 0},${g.activeChallenges || 0},"${g.providerName}"`);
}
writeFileSync(join(dataDir, 'stake_engine_games_categorized.csv'), csvLines.join('\n'));
console.log('✓ Saved to stake_engine_games_categorized.csv');
