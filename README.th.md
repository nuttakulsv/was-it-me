# was-it-me

[English](README.md) · จากคนทำ [receipts](https://github.com/nuttakulsv/receipts) และ [honest-tests](https://github.com/nuttakulsv/honest-tests)

> "The 3 remaining failures are pre-existing and unrelated to my changes."

coding agent ทุกตัวพูดประโยคนี้สักวัน บางครั้งก็จริง แต่บ่อยครั้งไม่จริง และกว่าจะรู้ก็ merge ไปแล้ว คนเราก็พูดเหมือนกัน ("เทสต์ตัวนั้นมัน flaky อยู่แล้ว")

was-it-me ช่วยตัดสินเรื่องนี้ มันรันคำสั่งที่ fail กับโค้ดที่เราแก้ แล้วไปรันอีกรอบใน git worktree ชั่วคราวที่ไม่มีโค้ดที่เราแก้ ฝั่งละหลายรอบ แล้วสรุปผลให้

```
$ python3 wasitme.py -- pytest tests/test_tax.py

was-it-me: `pytest tests/test_tax.py`

  with your changes:  FAIL FAIL FAIL
  without them:       pass pass pass    (base: 1a2b3c4, HEAD, i.e. without your uncommitted changes)

Verdict: YOURS. It fails every time with your changes (3 of 3) and passes every time without them.

Failing:
  tests/test_tax.py::test_rounding_half_even
```

| ผลตัดสิน | ความหมาย | Exit code |
|---|---|---|
| **PASSES** | ผ่าน ไม่มีอะไรต้องอธิบาย | 0 |
| **YOURS** | พังเฉพาะตอนมีโค้ดที่เราแก้ ถ้าไม่มีก็ผ่าน | 1 |
| **PARTLY YOURS** | พังทั้งสองฝั่ง แต่มีบางเทสต์ที่พังเฉพาะตอนมีโค้ดที่เราแก้ (บอกให้ด้วยว่าตัวไหน) | 1 |
| **PRE-EXISTING** | พังแบบเดียวกันแม้ไม่มีโค้ดที่เราแก้ | 0 |
| **FLAKY** | โค้ดเดียวกันแต่บางรอบผ่านบางรอบพัง และบอกด้วยว่าถ้าไม่มีโค้ดที่เราแก้เป็นแบบนี้ไหม | 3 |

มันอ่านชื่อเทสต์ที่ fail จาก output ของ pytest, Jest, Vitest, Go, cargo, RSpec, PHPUnit และ TAP ได้ เลยแยกได้ว่า "สองเทสต์เดิมพังบน main อยู่แล้ว" กับ "มีเทสต์พังเพิ่มอีกตัวเพราะเรา"

## วิธีใช้

ต้องมีแค่ `python3` กับ `git` ไม่ต้องติดตั้งอะไร

```
curl -O https://raw.githubusercontent.com/nuttakulsv/was-it-me/main/skills/was-it-me/wasitme.py

python3 wasitme.py -- npm test -- cart
python3 wasitme.py --runs 10 -- go test ./billing/ -run TestInvoice
python3 wasitme.py --base main -- bundle exec rspec spec/models/order_spec.rb
```

**เทียบกับอะไร** ถ้ามีงานที่ยังไม่ commit จะเทียบกับ `HEAD` ถ้าไม่มี จะเทียบกับจุดที่ branch แยกออกมาจาก `main` (หรือ `master`) ถ้าอยู่บน main อยู่แล้วจะเทียบกับ commit ก่อนหน้า หรือจะเลือกเองด้วย `--base` ก็ได้

**ไฟล์ของเราปลอดภัย** มันไม่ stash และไม่ checkout อะไรใน working tree ของเรา ฝั่งที่ไม่มีโค้ดที่เราแก้เป็น `git worktree` แยกอยู่ในโฟลเดอร์ชั่วคราว ใช้เสร็จก็ลบทิ้ง

**dependency** worktree ฝั่งนั้นจะได้ symlink ไปที่ `node_modules`, `.venv`, `vendor` และไฟล์ `.env` ที่เรามีอยู่ เทสต์จึงรันได้โดยไม่ต้องติดตั้งใหม่ สำหรับ Python จะตั้ง `PYTHONPATH` ให้ใช้โค้ดของฝั่งนั้นก่อน เพื่อไม่ให้ editable install แอบไปดึงโค้ดที่เราแก้มาใช้ ถ้าฝั่งนั้นรันไม่ขึ้นเลย (หา module ไม่เจอ, ไม่มีคำสั่ง) มันจะเตือน แทนที่จะสรุปว่าพังอยู่ก่อนแล้ว

## สำหรับ coding agent

มี skill ที่บอกให้ agent รัน was-it-me ก่อนจะอ้างว่าอะไร pre-existing หรือ flaky และบอกว่าแต่ละผลต้องทำอะไรต่อ (ถ้าเป็นความผิดของมันก็ต้องแก้ ห้ามใส่ retry หรือ skip เพื่อซ่อนเทสต์ที่ flaky)

Claude Code

```
/plugin marketplace add nuttakulsv/was-it-me
/plugin install was-it-me@was-it-me
```

Codex, Cursor หรือ agent อื่นที่อ่าน SKILL.md ได้

```
npx skills add nuttakulsv/was-it-me
```

ใช้คู่กับ [receipts](https://github.com/nuttakulsv/receipts) ได้ดี ตัวนั้นจะส่ง agent กลับไปถ้ามันอ้างว่าเทสต์พังอยู่ก่อนแล้วโดยที่ยังไม่ได้เช็ค

## ข้อจำกัด

- ใน monorepo ที่ workspace package ถูก symlink อยู่ใน `node_modules` ตัว `node_modules` ที่แชร์กันจะชี้กลับไปที่ package ที่เราแก้ ให้ใช้ `--setup 'pnpm install --frozen-lockfile'` (หรือ `npm ci`) เพื่อติดตั้งใหม่ใน worktree ฝั่งนั้น
- คำสั่งจะถูกรันเป็นสองเท่าของ `--runs` ถ้าชุดเทสต์ช้า ให้เลือกเฉพาะเทสต์ที่พังก่อน
- รันแค่สามรอบพิสูจน์ไม่ได้ว่าเทสต์ไม่ flaky ถ้าเรื่องนี้สำคัญให้ใช้ `--runs 20`
- เทสต์ที่ใช้ของร่วมกันนอก repo (ฐานข้อมูลในเครื่อง, port ตายตัว) อาจรบกวนกันระหว่างสองฝั่ง

## รันเทสต์

```
python3 skills/was-it-me/wasitme.py --test
```

## License

MIT
