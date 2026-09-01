import { animate, stagger } from "animejs";

// ==========================================================
// Central animation helpers for Nexara.
//
// Every function checks `prefers-reduced-motion` and returns
// immediately when the user has opted out of animation.
// ==========================================================

const REDUCED =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Animate a single element: fade-in + slide-up.
 * Used for new message bubbles appearing.
 */
export function animateBubbleIn(el) {
    if (REDUCED || !el) return;
    animate(el, {
        opacity: [0, 1],
        y: [12, 0],
        duration: 180,
        ease: "outQuad",
    });
}

/**
 * Pulse the send button after a message is sent.
 */
export function animateSendPulse(el) {
    if (REDUCED || !el) return;
    animate(el, {
        scale: [1, 1.25, 1],
        duration: 260,
        ease: "inOutQuad",
    });
}

/**
 * Animate a modal entering the viewport.
 * Returns a timeline that can be reversed for close.
 */
export function animateModalOpen(contentEl, overlayEl) {
    if (REDUCED || !contentEl) return null;

    const tl = animate({
        targets: overlayEl,
        opacity: [0, 1],
        duration: 200,
        ease: "outQuad",
    });

    animate(contentEl, {
        opacity: [0, 1],
        scale: [0.95, 1],
        duration: 220,
        ease: "outQuad",
    });

    return tl;
}

/**
 * Pop + bounce animation for a reaction chip.
 */
export function animateReactionPop(el) {
    if (REDUCED || !el) return;
    animate(el, {
        scale: [0, 1.3, 1],
        duration: 300,
        ease: "outElastic(1, 0.5)",
    });
}

/**
 * Staggered entrance for a list of elements.
 * Used for conversation items, reaction chips, etc.
 */
export function animateStaggeredList(elements, opts = {}) {
    if (REDUCED || !elements?.length) return;
    animate(elements, {
        opacity: [0, 1],
        y: [8, 0],
        delay: stagger(30),
        duration: 200,
        ease: "outQuad",
        ...opts,
    });
}
