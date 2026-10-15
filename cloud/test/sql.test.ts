// Fix-1: every SQL statement the routes emit must prepare against the real
// migration schema. The D1 fakes match SQL by prefix, so a wrong column name
// would pass route tests and fail on D1. This test extracts all static
// prepare("...") strings from cloud/src and EXPLAINs each one in node:sqlite
// loaded with migrations/0001_init.sql.

import { describe, expect, it } from "vitest";
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function tsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, name.name);
    if (name.isDirectory()) out.push(...tsFiles(p));
    else if (p.endsWith(".ts")) out.push(p);
  }
  return out;
}

/** Extract double-quoted literals concatenated after .prepare( calls. */
function extractSql(source: string): string[] {
  const found: string[] = [];
  const re = /\.prepare\(\s*/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    let i = m.index + m[0].length;
    let sql = "";
    for (;;) {
      while (i < source.length && /\s/.test(source[i]!)) i++;
      if (source[i] !== '"') break;
      i++;
      let lit = "";
      while (i < source.length && source[i] !== '"') {
        if (source[i] === "\\") {
          lit += source[i + 1] ?? "";
          i += 2;
        } else {
          lit += source[i];
          i++;
        }
      }
      if (source[i] !== '"') break; // unterminated: not static SQL
      i++;
      sql += lit;
      while (i < source.length && /\s/.test(source[i]!)) i++;
      if (source[i] === "+") {
        i++;
        continue;
      }
      break;
    }
    if (sql) found.push(sql);
  }
  return found;
}

describe("route SQL prepares against the migration schema", () => {
  it("EXPLAINs every static statement (tables + columns must exist)", () => {
    const schema = readFileSync(join(root, "migrations", "0001_init.sql"), "utf8");
    const db = new DatabaseSync(":memory:");
    db.exec(schema);
    const stmts: Array<{ file: string; sql: string }> = [];
    for (const file of tsFiles(join(root, "src"))) {
      for (const sql of extractSql(readFileSync(file, "utf8"))) {
        if (/^\s*(SELECT|INSERT|UPDATE|DELETE)\b/i.test(sql)) stmts.push({ file, sql });
      }
    }
    expect(stmts.length).toBeGreaterThan(30);
    const failures: string[] = [];
    for (const { file, sql } of stmts) {
      try {
        db.prepare(`EXPLAIN ${sql}`);
      } catch (err) {
        failures.push(`${file.split("cloud")[1]}: ${sql.slice(0, 90)} … (${(err as Error).message})`);
      }
    }
    db.close();
    expect(failures).toEqual([]);
  });
});
