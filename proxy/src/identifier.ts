import { randomBytes, createHash } from "node:crypto";

const IDENT_LENGTH = 26;
const CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
const TIME_BYTE_COUNT = 6;
const RANDOM_PART_LENGTH = IDENT_LENGTH - TIME_BYTE_COUNT * 2;

let lastTimestamp = 0;
let counter = 0;

function create(descending: boolean, timestamp = Date.now()): string {
  if (timestamp !== lastTimestamp) {
    lastTimestamp = timestamp;
    counter = 0;
  }
  counter++;

  const current = BigInt(timestamp) * 0x1000n + BigInt(counter);
  const value = descending ? ~current : current;

  const time = Array.from({ length: TIME_BYTE_COUNT }, (_, index) =>
    Number((value >> BigInt(40 - 8 * index)) & 0xffn)
      .toString(16)
      .padStart(2, "0")
  ).join("");

  const bytes = randomBytes(RANDOM_PART_LENGTH);
  const random = Array.from(bytes, (byte) => CHARS[byte % 62]).join("");

  return time + random;
}

export function ascending(): string {
  return create(false);
}

export function descending(): string {
  return create(true);
}

export function sessionId(): string {
  return "ses_" + descending();
}

export function requestId(): string {
  return "msg_" + ascending();
}

export function projectId(dir: string): string {
  const hash = createHash("sha256").update(dir).digest();
  const timePart = Array.from({ length: 6 }, (_, i) =>
    hash[i].toString(16).padStart(2, "0")
  ).join("");
  const randomPart = Array.from({ length: RANDOM_PART_LENGTH }, (_, i) =>
    CHARS[hash[6 + i] % 62]
  ).join("");
  return "prj_" + timePart + randomPart;
}