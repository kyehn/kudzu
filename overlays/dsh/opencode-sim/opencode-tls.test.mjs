// TLS ClientHello 断言测试：逐维度比对
// overlays/reasonix/opencode/_tls-fingerprint.json 的基准抓包。
//
// 可配置维度（ciphers / groups / sigalgs / versions / ALPN）逐字节断言；
// 扩展线序差异（Node/OpenSSL 栈 vs BoringSSL）如实报告并断言已知差异，
// 不虚报为一致。
//
// 运行：node --test opencode-tls.test.mjs
//   - 默认用当前 node + 本目录 openssl.cnf；可用 DSH_NODE / OPENSSL_CNF 覆盖。

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import net from "node:net";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const NODE = process.env.DSH_NODE ?? process.execPath;
const CNF = process.env.OPENSSL_CNF ?? join(HERE, "openssl.cnf");

// 基准（来源：overlays/reasonix/opencode/_tls-fingerprint.json，只读不修改）
//   ja3_string = "771,1301,1302,1303,c02b,c02f,c02c,c030,cca9,cca8,c009,c013,
//                 c00a,c014,9c,9d,2f,35,17,ff01,a,b,23,10,5,d,12,33,2d,2b,1d,17,18,0"
//   ja4_extra.groups = [29,23,24]
//   ja4_extra.sigalgs = [1027,2052,1025,1283,2053,1281,2054,1537,513]
//     （1027=0x0403 ecdsa_secp256r1_sha256, ..., 513=0x0201 rsa_pkcs1_sha1）
//   基准 9 项含 0x0201(rsa_pkcs1_sha1)；OpenSSL 3.x 在 ClientHello 中过滤该
//   算法（node 22/24 与 openssl s_client -security_level 0 均实测验证），
//   故 sigalgs 断言基准前 8 项，0201 缺席作为已知限制如实记录。
const REF = {
  ciphers: [
    0x1301, 0x1302, 0x1303, 0xc02b, 0xc02f, 0xc02c, 0xc030, 0xcca9, 0xcca8,
    0xc009, 0xc013, 0xc00a, 0xc014, 0x9c, 0x9d, 0x2f, 0x35,
  ],
  groups: [29, 23, 24],
  sigalgs: [0x0403, 0x0804, 0x0401, 0x0503, 0x0805, 0x0501, 0x0806, 0x0601],
  versions: [0x0304, 0x0303], // TLS1.3, TLS1.2
  alpn: ["http/1.1"],
  // 基准扩展段（ja3_string 顺序）：23(extended_master_secret), 65281(reneg_info),
  // 10(groups), 11(ec_point_formats), 35(session_ticket), 16(alpn),
  // 5(status_request), 13(sigalgs), 18(SCT), 51(key_share), 45(psk_modes),
  // 43(versions)
  extTypes: [23, 65281, 10, 11, 35, 16, 5, 13, 18, 51, 45, 43],
};

// 与 opencode-sim.mjs 的 TLS_CIPHERS 逐项一致（修改时两处同步）。
const TLS_CIPHERS = [
  // TLS 1.3（0x1301 0x1302 0x1303）
  "TLS_AES_128_GCM_SHA256",
  "TLS_AES_256_GCM_SHA384",
  "TLS_CHACHA20_POLY1305_SHA256",
  // TLS 1.2：0xC02B 0xC02F 0xC02C 0xC030（ECDHE GCM）
  "ECDHE-ECDSA-AES128-GCM-SHA256",
  "ECDHE-RSA-AES128-GCM-SHA256",
  "ECDHE-ECDSA-AES256-GCM-SHA384",
  "ECDHE-RSA-AES256-GCM-SHA384",
  // 0xCCA9 0xCCA8（CHACHA20）
  "ECDHE-ECDSA-CHACHA20-POLY1305",
  "ECDHE-RSA-CHACHA20-POLY1305",
  // 0xC009 0xC013 0xC00A 0xC014（ECDHE SHA1）
  "ECDHE-ECDSA-AES128-SHA",
  "ECDHE-RSA-AES128-SHA",
  "ECDHE-ECDSA-AES256-SHA",
  "ECDHE-RSA-AES256-SHA",
  // 0x009C 0x009D 0x002F 0x0035（RSA）
  "AES128-GCM-SHA256",
  "AES256-GCM-SHA384",
  "AES128-SHA",
  "AES256-SHA",
].join(":");

const PORT = 19449;

/** 起本地 TCP server 抓 ClientHello，spawn 目标 node（--openssl-config）发起连接。 */
function captureClientHello() {
  return new Promise((resolve, reject) => {
    const server = net.createServer((sock) => {
      let buf = Buffer.alloc(0);
      sock.on("data", (d) => {
        buf = Buffer.concat([buf, d]);
        if (buf.length < 5) return;
        const recLen = buf.readUInt16BE(3);
        if (buf.length < 5 + recLen) return;
        const hs = buf.subarray(5, 5 + recLen);
        const hsLen = (hs[1] << 16) | (hs[2] << 8) | hs[3];
        const body = hs.subarray(4, 4 + hsLen);
        let p = 2 + 32;
        const sidLen = body[p];
        p += 1 + sidLen;
        const csLen = body.readUInt16BE(p);
        p += 2;
        const ciphers = [];
        for (let i = 0; i < csLen; i += 2)
          ciphers.push(body.readUInt16BE(p + i));
        p += csLen;
        const compLen = body[p];
        p += 1 + compLen;
        const extLen = body.readUInt16BE(p);
        p += 2;
        const exts = new Map();
        const end = p + extLen;
        const order = [];
        while (p < end) {
          const t = body.readUInt16BE(p);
          const l = body.readUInt16BE(p + 2);
          exts.set(t, body.subarray(p + 4, p + 4 + l));
          order.push(t);
          p += 4 + l;
        }
        // RFC 8446：groups/sigalgs/alpn 的 extension_data 是 uint16 vector
        // （前 2 字节长度）；versions 是 uint8 vector（前 1 字节长度）
        const read16 = (t, off) => {
          const b = exts.get(t) ?? Buffer.alloc(0);
          const out = [];
          for (let i = off; i + 1 < b.length; i += 2)
            out.push(b.readUInt16BE(i));
          return out;
        };
        const alpnBuf = exts.get(16) ?? Buffer.alloc(0);
        const alpn = [];
        for (let i = 2; i < alpnBuf.length; ) {
          const l = alpnBuf[i];
          alpn.push(alpnBuf.subarray(i + 1, i + 1 + l).toString());
          i += 1 + l;
        }
        sock.destroy();
        server.close();
        resolve({
          ciphers,
          groups: read16(10, 2),
          sigalgs: read16(13, 2),
          versions: read16(43, 1),
          alpn,
          extOrder: order,
        });
      });
    });
    server.on("error", reject);
    server.listen(PORT, () => {
      const client = `
        const tls = require("tls");
        tls.connect({
          host: "127.0.0.1", port: ${PORT}, rejectUnauthorized: false,
          minVersion: "TLSv1.2", maxVersion: "TLSv1.3",
          ciphers: ${JSON.stringify(TLS_CIPHERS)},
          ecdhCurve: "X25519:prime256v1:secp384r1",
          ALPNProtocols: ["http/1.1"],
        });
        setTimeout(() => process.exit(0), 3000);
      `;
      const child = spawn(NODE, [`--openssl-config=${CNF}`, "-e", client], {
        stdio: "ignore",
      });
      child.on("error", reject);
      setTimeout(() => {
        server.close();
        reject(new Error("timeout: no ClientHello captured"));
      }, 5000).unref();
    });
  });
}

test("ciphers 与基准 17 项逐字节一致", async () => {
  const { ciphers } = await captureClientHello();
  assert.deepEqual(ciphers, REF.ciphers);
});

test("supported_groups = [29,23,24]（X25519, prime256v1, secp384r1）", async () => {
  const { groups } = await captureClientHello();
  assert.deepEqual(groups, REF.groups);
});

test("signature_algorithms 前 8 项与基准一致（0201 被 OpenSSL 过滤）", async () => {
  const { sigalgs } = await captureClientHello();
  // 如实记录：基准 9 项含 0x0201(rsa_pkcs1_sha1)，OpenSSL 3.x 在 ClientHello
  // 构造中过滤该算法（node 22/24 与 openssl s_client 3.0.13 实测），不可配置。
  assert.deepEqual(sigalgs, REF.sigalgs);
});

test("supported_versions = [TLS1.3, TLS1.2]", async () => {
  const { versions } = await captureClientHello();
  assert.deepEqual(versions, REF.versions);
});

test("ALPN = [http/1.1]", async () => {
  const { alpn } = await captureClientHello();
  assert.deepEqual(alpn, REF.alpn);
});

test("扩展线序差异如实报告（不虚报）", async () => {
  const { extOrder } = await captureClientHello();
  // Node/OpenSSL 栈的扩展集合与 BoringSSL 基准的差异是硬限制：
  //   - Node 多发 encrypt_then_mac(22)（基准无）
  //   - Node 缺 status_request(5) 与 SCT(18)（基准有）
  // 其余扩展类型一致。此断言把该差异固化为文档化的已知行为，
  // 若未来 OpenSSL 行为变化，此测试会失败并提示重新评估。
  const missing = REF.extTypes.filter((t) => !extOrder.includes(t));
  const extra = extOrder.filter((t) => !REF.extTypes.includes(t));
  // eslint-disable-next-line no-console
  console.log(
    `[known TLS extension differences] extra(OpenSSL-only): ${extra.join(",")}; ` +
      `missing(BoringSSL-only): ${missing.join(",")}`,
  );
  assert.deepEqual(extra, [22]); // encrypt_then_mac
  assert.deepEqual(missing, [5, 18]); // status_request, SCT
});
