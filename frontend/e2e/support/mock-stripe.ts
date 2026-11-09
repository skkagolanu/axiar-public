import type { Page } from '@playwright/test';

// need a human-provisioned Stripe account + GitHub secrets), and CardElement renders
// inside a CDN-hosted iframe that needs a live stripe.js connection to mount at all --
// so this replaces the *entire* stripe.js script with a minimal fake implementing just
// the surface @stripe/react-stripe-js and BookPage.tsx actually call: elements.create,
// element.mount/on, and stripe.confirmCardPayment (always resolves "succeeded"). This
// exercises the real app code paths (Elements provider, CardElement lifecycle, the
// booking + payment-intent requests) without depending on Stripe's real network/iframe.
const FAKE_STRIPE_JS = `
(function () {
  function makeElement() {
    var handlers = {};
    return {
      mount: function (target) {
        var node = typeof target === 'string' ? document.querySelector(target) : target;
        if (!node) return;
        var input = document.createElement('input');
        input.setAttribute('data-testid', 'fake-card-element');
        input.placeholder = 'Fake card number (E2E mock)';
        node.appendChild(input);
        setTimeout(function () { if (handlers.ready) handlers.ready(); }, 0);
      },
      on: function (event, handler) { handlers[event] = handler; },
      off: function () {},
      unmount: function () {},
      update: function () {},
      focus: function () {},
      blur: function () {},
      clear: function () {},
    };
  }

  function makeElements() {
    var cardElement = null;
    return {
      create: function (type) {
        cardElement = makeElement();
        return cardElement;
      },
      getElement: function () {
        return cardElement;
      },
    };
  }

  window.Stripe = function (_publicKey) {
    return {
      elements: function () { return makeElements(); },
      confirmCardPayment: function (_clientSecret) {
        return Promise.resolve({ paymentIntent: { id: 'pi_e2e_fake', status: 'succeeded' } });
      },
      // react-stripe-js's isStripe() check requires all four of these to be
      // functions before it will accept the object as a valid stripe prop at all
      // (otherwise it throws an "Invalid prop stripe supplied to Elements" error) --
      // unused by this app, but must exist.
      createToken: function () { return Promise.resolve({}); },
      createPaymentMethod: function () { return Promise.resolve({}); },
    };
  };
})();
`;

export async function installStripeMock(page: Page): Promise<void> {
  // @stripe/stripe-js requests https://js.stripe.com/<release-train>/stripe.js (the
  // release-train segment -- e.g. "v3" or a codename like "dahlia" -- changes across
  // package versions), so match broadly rather than pin an exact path.
  await page.route('https://js.stripe.com/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/javascript', body: FAKE_STRIPE_JS })
  );
}
