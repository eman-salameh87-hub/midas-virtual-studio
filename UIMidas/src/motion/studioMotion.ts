import { useEffect, type RefObject } from "react";
import { flushSync } from "react-dom";

export function useAmbientStudioLight(stageRef: RefObject<HTMLDivElement | null>, active: boolean) {
  useEffect(() => {
    const stage = stageRef.current;
    if (!active || !stage || !canFollowPointer()) return;

    const reach = window.matchMedia("(max-width: 1100px)").matches ? 0.28 : 0.5;
    const restX = 0.3;
    const restY = 0.18;
    let targetX = restX;
    let targetY = restY;
    let currentX = restX;
    let currentY = restY;
    let frame = 0;
    let running = false;

    const glow = stage.querySelector<HTMLElement>(".stage__glow");
    if (!glow) return;

    const paint = () => {
      glow.style.setProperty("--glow-x", `${(currentX * 100).toFixed(2)}%`);
      glow.style.setProperty("--glow-y", `${(currentY * 100).toFixed(2)}%`);
    };

    const tick = () => {
      currentX += (targetX - currentX) * 0.045;
      currentY += (targetY - currentY) * 0.045;
      paint();
      if (Math.hypot(targetX - currentX, targetY - currentY) < 0.0015) {
        currentX = targetX;
        currentY = targetY;
        paint();
        running = false;
        return;
      }
      frame = requestAnimationFrame(tick);
    };

    const start = () => {
      if (running) return;
      running = true;
      frame = requestAnimationFrame(tick);
    };

    let bounds = stage.getBoundingClientRect();
    const refreshBounds = () => {
      bounds = stage.getBoundingClientRect();
    };

    const onMove = (event: PointerEvent) => {
      if (bounds.width === 0 || bounds.height === 0) return;
      const px = (event.clientX - bounds.left) / bounds.width;
      const py = (event.clientY - bounds.top) / bounds.height;
      const nextX = restX + (px - restX) * reach;
      const nextY = restY + (py - restY) * reach;
      if (Math.abs(nextX - targetX) < 0.004 && Math.abs(nextY - targetY) < 0.004) return;
      targetX = nextX;
      targetY = nextY;
      start();
    };

    const pause = () => {
      running = false;
      cancelAnimationFrame(frame);
    };

    stage.addEventListener("pointermove", onMove, { passive: true });
    stage.addEventListener("pointerdown", pause, { passive: true });
    window.addEventListener("resize", refreshBounds);
    return () => {
      stage.removeEventListener("pointermove", onMove);
      stage.removeEventListener("pointerdown", pause);
      window.removeEventListener("resize", refreshBounds);
      cancelAnimationFrame(frame);
      glow.style.removeProperty("--glow-x");
      glow.style.removeProperty("--glow-y");
    };
  }, [active, stageRef]);
}

export function useMagneticCards(rootRef: RefObject<HTMLElement | null>, selector: string) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root || !canTrackPointer()) return;

    const max = window.matchMedia("(max-width: 1100px)").matches ? 3 : 5;
    const cards = [...root.querySelectorAll<HTMLElement>(selector)];
    const stops = cards.map((card) => bindMagneticCard(card, max));
    return () => {
      for (const stop of stops) stop();
    };
  }, [rootRef, selector]);
}

export function runStudioStepTransition(enabled: boolean, update: () => void) {
  const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const startViewTransition = document.startViewTransition?.bind(document);
  if (!enabled || reduced || !startViewTransition) {
    update();
    return;
  }
  document.documentElement.dataset.stepFlow = "1";
  document.documentElement.dataset.stepSettle = "1";
  const transition = startViewTransition(() => {
    flushSync(update);
  });
  void transition.finished.finally(() => {
    delete document.documentElement.dataset.stepFlow;
    delete document.documentElement.dataset.stepSettle;
  });
}

function canFollowPointer() {
  return canTrackPointer();
}

function canTrackPointer() {
  if (typeof window.matchMedia !== "function") return false;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
  if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return false;
  if (window.matchMedia("(max-width: 700px)").matches) return false;
  return true;
}

function bindMagneticCard(card: HTMLElement, max: number) {
  let frame = 0;
  let tx = 0;
  let ty = 0;
  let cx = 0;
  let cy = 0;
  let rect = card.getBoundingClientRect();
  let running = false;

  let painted = "";

  const paint = (clear: boolean) => {
    if (clear) {
      if (painted === "") return;
      painted = "";
      card.style.transform = "";
      return;
    }
    const turn = (cx / max) * 0.5;
    const next = `translate3d(${cx.toFixed(2)}px, ${cy.toFixed(2)}px, 0) rotate(${turn.toFixed(3)}deg)`;
    if (next === painted) return;
    painted = next;
    card.style.transform = next;
  };

  const tick = () => {
    cx += (tx - cx) * 0.18;
    cy += (ty - cy) * 0.18;
    const settled = Math.hypot(tx - cx, ty - cy) < 0.08;
    if (settled) {
      cx = tx;
      cy = ty;
      paint(tx === 0 && ty === 0);
      running = false;
      return;
    }
    paint(false);
    frame = requestAnimationFrame(tick);
  };

  const start = () => {
    if (running) return;
    running = true;
    frame = requestAnimationFrame(tick);
  };

  const onEnter = () => {
    rect = card.getBoundingClientRect();
  };

  const onMove = (event: PointerEvent) => {
    const px = (event.clientX - rect.left) / rect.width - 0.5;
    const py = (event.clientY - rect.top) / rect.height - 0.5;
    tx = clamp(px * max * 2, max);
    ty = clamp(py * max * 2, max);
    start();
  };

  const onLeave = () => {
    tx = 0;
    ty = 0;
    start();
  };

  const pause = () => {
    running = false;
    cancelAnimationFrame(frame);
  };

  card.addEventListener("pointerenter", onEnter);
  card.addEventListener("pointermove", onMove, { passive: true });
  card.addEventListener("pointerdown", pause, { passive: true });
  card.addEventListener("pointerleave", onLeave);
  card.addEventListener("pointercancel", onLeave);
  return () => {
    card.removeEventListener("pointerenter", onEnter);
    card.removeEventListener("pointermove", onMove);
    card.removeEventListener("pointerdown", pause);
    card.removeEventListener("pointerleave", onLeave);
    card.removeEventListener("pointercancel", onLeave);
    cancelAnimationFrame(frame);
    card.style.transform = "";
  };
}

function clamp(value: number, max: number) {
  return Math.max(-max, Math.min(max, value));
}
