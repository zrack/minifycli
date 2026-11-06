// Deliberately failing pilot fixture for a disposable snapshot only.
// It is not a defect in the repository being evaluated.
import assert from "node:assert/strict";
import test from "node:test";

test("pilot pass", () => {
  assert.equal(2 + 2, 4);
});

test("pilot controlled failure", () => {
  console.log("✓ migration completed (2 ms)");
  assert.equal(42, 41, "MINIFYCLI_PILOT_JS_ASSERTION");
});
