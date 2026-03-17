/**
 * AITuber Minecraft Bridge Bot — FR-GAME-05 (Phase 1)
 *
 * This Node.js script:
 *   1. Connects to a Minecraft server via Mineflayer.
 *   2. Exposes a WebSocket server on WS_PORT (default 31901).
 *   3. Streams game_state JSON to all connected orchestrator clients.
 *   4. Receives action_cmd JSON from the orchestrator and executes them
 *      via the Mineflayer API.
 *
 * Environment variables:
 *   MC_HOST         Minecraft server host     (default: localhost)
 *   MC_PORT         Minecraft server port     (default: 25565)
 *   MC_USERNAME     Bot Minecraft username    (default: AITuberBot)
 *   MC_PASSWORD     Bot Minecraft password    (optional, for online mode)
 *   MC_VERSION      Minecraft version string  (default: auto-detect)
 *   WS_PORT         WebSocket port            (default: 31901)
 *   STATE_INTERVAL  game_state emit interval ms (default: 500)
 */

'use strict';

const mineflayer = require('mineflayer');
const { WebSocketServer, WebSocket } = require('ws');

// ── Config ─────────────────────────────────────────────────────────────────────

const MC_HOST = process.env.MC_HOST || 'localhost';
const MC_PORT = parseInt(process.env.MC_PORT || '25565', 10);
const MC_USERNAME = process.env.MC_USERNAME || 'AITuberBot';
const MC_PASSWORD = process.env.MC_PASSWORD || undefined;
const MC_VERSION = process.env.MC_VERSION || undefined;
const WS_PORT = parseInt(process.env.WS_PORT || '31901', 10);
const STATE_INTERVAL_MS = parseInt(process.env.STATE_INTERVAL || '500', 10);

// ── WebSocket server ──────────────────────────────────────────────────────────

const wss = new WebSocketServer({ port: WS_PORT });
console.log(`[Bridge] WebSocket server listening on ws://0.0.0.0:${WS_PORT}`);

/** Broadcast a JSON message to all connected orchestrator clients. */
function broadcast(type, payload) {
  const msg = JSON.stringify({ type, payload });
  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) {
      client.send(msg);
    }
  }
}

// ── Mineflayer bot ────────────────────────────────────────────────────────────

let bot = null;

function createBot() {
  const opts = {
    host: MC_HOST,
    port: MC_PORT,
    username: MC_USERNAME,
    version: MC_VERSION,
  };
  if (MC_PASSWORD) {
    opts.password = MC_PASSWORD;
  }

  bot = mineflayer.createBot(opts);

  bot.once('spawn', () => {
    console.log(`[Bridge] Bot spawned as "${bot.username}"`);
    startStateEmitter();
  });

  bot.on('chat', (username, message) => {
    if (username === bot.username) return;
    broadcast('event', { event: 'chat', username, message });
  });

  bot.on('death', () => {
    broadcast('event', { event: 'death', username: bot.username });
  });

  bot.on('entityHurt', (entity) => {
    if (entity === bot.entity) {
      broadcast('event', {
        event: 'player_hurt',
        health: bot.health,
        cause: 'unknown',
      });
    }
  });

  bot.on('error', (err) => {
    console.error('[Bridge] Bot error:', err.message);
  });

  bot.on('end', (reason) => {
    console.log(`[Bridge] Bot disconnected: ${reason}. Reconnecting in 5 s…`);
    setTimeout(createBot, 5000);
  });
}

// ── State emitter ─────────────────────────────────────────────────────────────

let stateTimer = null;

function startStateEmitter() {
  if (stateTimer) return;
  stateTimer = setInterval(() => {
    if (!bot || !bot.entity) return;

    /** @type {{ type: string, distance: number }[]} */
    const nearbyEntities = [];
    for (const entity of Object.values(bot.entities)) {
      if (!entity || entity === bot.entity) continue;
      const dist = bot.entity.position.distanceTo(entity.position);
      if (dist > 24) continue;
      const isHostile = entity.type === 'mob' && isHostileMob(entity.name || '');
      nearbyEntities.push({
        id: entity.id,
        name: entity.name || 'unknown',
        type: isHostile ? 'hostile' : entity.type,
        distance: Math.round(dist * 10) / 10,
        pos: {
          x: Math.round(entity.position.x),
          y: Math.round(entity.position.y),
          z: Math.round(entity.position.z),
        },
      });
    }

    /** @type {Array<{name:string,count:number}>} */
    const inventory = (bot.inventory.items() || []).map((item) => ({
      name: item.name,
      count: item.count,
    }));

    const pos = bot.entity.position;
    const state = {
      username: bot.username,
      health: bot.health,
      max_health: 20,
      food: bot.food,
      pos: {
        x: Math.round(pos.x * 10) / 10,
        y: Math.round(pos.y * 10) / 10,
        z: Math.round(pos.z * 10) / 10,
      },
      time: bot.time.timeOfDay,
      nearby_entities: nearbyEntities,
      inventory,
      biome: bot.blockAt(pos) ? (bot.blockAt(pos).biome || {}).name || 'unknown' : 'unknown',
    };

    broadcast('game_state', state);
  }, STATE_INTERVAL_MS);
}

// ── Hostile mob list (Minecraft 1.21 baseline) ────────────────────────────────

const HOSTILE_MOBS = new Set([
  'zombie', 'skeleton', 'creeper', 'spider', 'cave_spider', 'witch',
  'enderman', 'blaze', 'ghast', 'magma_cube', 'slime', 'pillager',
  'ravager', 'vindicator', 'evoker', 'vex', 'phantom', 'drowned',
  'husk', 'stray', 'warden', 'elder_guardian', 'guardian', 'shulker',
]);

function isHostileMob(name) {
  return HOSTILE_MOBS.has(name.toLowerCase().replace(/ /g, '_'));
}

// ── Action executor ───────────────────────────────────────────────────────────

wss.on('connection', (ws, req) => {
  const addr = req.socket.remoteAddress;
  console.log(`[Bridge] Orchestrator connected from ${addr}`);

  ws.on('message', async (data) => {
    let cmd;
    try {
      cmd = JSON.parse(data.toString());
    } catch (_) {
      console.warn('[Bridge] Received non-JSON message, ignoring');
      return;
    }
    await executeAction(cmd);
  });

  ws.on('close', () => {
    console.log(`[Bridge] Orchestrator disconnected: ${addr}`);
  });
});

/**
 * Execute a single action_cmd dict received from the orchestrator.
 *
 * Supported types:
 *   move        args: { direction?, destination?, sprint? }
 *   attack      args: { target }
 *   use_item    args: { item }
 *   chat        args: { message }
 *   look        args: { entity_id? }
 */
async function executeAction(cmd) {
  if (!bot || !bot.entity) return;
  const { type, args = {} } = cmd;

  try {
    switch (type) {
      case 'move': {
        if (args.direction === 'away_from_threat') {
          // Simple: stop current navigation and steer away
          bot.clearControlStates();
          bot.setControlState('back', true);
          if (args.sprint) bot.setControlState('sprint', true);
          setTimeout(() => {
            bot.clearControlStates();
          }, 1000);
        }
        break;
      }

      case 'attack': {
        if (args.target === 'nearest_hostile') {
          const hostile = findNearestHostile();
          if (hostile) {
            bot.attack(hostile);
          }
        } else {
          const target = bot.entities[args.target_id];
          if (target) bot.attack(target);
        }
        break;
      }

      case 'use_item': {
        const itemName = args.item;
        const item = bot.inventory.findInventoryItem(
          bot.registry.itemsByName[itemName]?.id,
          null
        );
        if (item) {
          await bot.equip(item, 'hand');
          await bot.consume();
        }
        break;
      }

      case 'chat': {
        const msg = String(args.message || '').slice(0, 256);
        if (msg) bot.chat(msg);
        break;
      }

      default:
        console.warn(`[Bridge] Unknown action type: ${type}`);
    }
  } catch (err) {
    console.error(`[Bridge] Action "${type}" failed:`, err.message);
  }
}

function findNearestHostile() {
  let nearest = null;
  let nearestDist = Infinity;
  for (const entity of Object.values(bot.entities)) {
    if (!entity || entity === bot.entity) continue;
    if (!isHostileMob(entity.name || '')) continue;
    const dist = bot.entity.position.distanceTo(entity.position);
    if (dist < nearestDist) {
      nearestDist = dist;
      nearest = entity;
    }
  }
  return nearest;
}

// ── Entry point ───────────────────────────────────────────────────────────────

createBot();
