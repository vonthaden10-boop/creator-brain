require('dotenv').config();
const { Client } = require('pg');
const fs = require('fs');
const path = require('path');

const url = new URL(process.env.SUPABASE_URL);
const projectRef = url.hostname.split('.')[0];

const isPooler = (process.env.DATABASE_HOST || '').includes('pooler.supabase.com');
const client = new Client({
  host: process.env.DATABASE_HOST || `db.${projectRef}.supabase.co`,
  port: isPooler ? 6543 : 5432,
  database: 'postgres',
  user: isPooler ? `postgres.${projectRef}` : 'postgres',
  password: process.env.DATABASE_PASSWORD,
  ssl: { rejectUnauthorized: false },
});

async function run() {
  const sql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');

  // Split on semicolons, filter blanks and comments-only blocks
  const statements = sql
    .split(';')
    .map(s => s.trim())
    .filter(s => s.length > 0 && !s.startsWith('--'));

  await client.connect();
  console.log('Connected to Supabase PostgreSQL');

  for (const statement of statements) {
    try {
      await client.query(statement);
      const match = statement.match(/(create\s+\w+\s+(?:if\s+not\s+exists\s+)?(\w+))/i);
      console.log(`OK: ${match ? match[0] : statement.slice(0, 60)}`);
    } catch (err) {
      console.error(`FAILED: ${statement.slice(0, 80)}`);
      console.error(`  ${err.message}`);
    }
  }

  await client.end();
  console.log('\nSchema setup complete.');
}

run().catch(err => {
  console.error('Connection failed:', err.message);
  console.error('\nAdd DATABASE_PASSWORD to your .env file.');
  console.error('Find it in: Supabase Dashboard → Project Settings → Database → Database password');
  process.exit(1);
});
