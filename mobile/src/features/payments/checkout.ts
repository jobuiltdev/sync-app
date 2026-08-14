import { ApiError } from '@/api/errors';

/**
 * Paying for a booking, from the customer's side.
 *
 * Checkout happens on the payment provider's own hosted page, opened in the
 * system browser. That is a deliberate choice rather than a limitation: card
 * details never touch this app, so no build of it is ever in scope for PCI, and
 * the app holds no provider credential of any kind. It also needs no native
 * module, which keeps the project on Expo SDK 54 and runnable in Expo Go.
 *
 * The page is opened with `Linking.openURL`, from `expo-linking`, which the
 * project already depends on. An in-app browser would need `expo-web-browser`,
 * a package this app does not have and does not need: the system browser
 * returns to the app through the `sync://` scheme already configured in
 * app.json.
 *
 * Nothing the browser reports is trusted. When the customer comes back the app
 * asks the server to check, and the server asks the provider.
 */
export type PaymentFailure =
  | 'NOT_PAYABLE'
  | 'GONE'
  | 'AMOUNT_MISMATCH'
  | 'CONNECTION'
  | 'UNKNOWN';

export interface PaymentOutcome {
  failure: PaymentFailure;
  message: string;
  /** Whether sending the same request again could succeed. */
  isRetryable: boolean;
}

const BY_CODE: Record<string, PaymentFailure> = {
  BOOKING_NOT_PAYABLE: 'NOT_PAYABLE',
  PAYMENT_NOT_FOUND: 'GONE',
  NOT_FOUND: 'GONE',
  PAYMENT_AMOUNT_MISMATCH: 'AMOUNT_MISMATCH',
};

//: Only a dropped connection is worth sending again unchanged. A booking that
//: cannot be paid for will not become payable by asking twice, and an amount
//: mismatch needs a person to look at it.
const RETRYABLE: ReadonlySet<PaymentFailure> = new Set<PaymentFailure>(['CONNECTION', 'UNKNOWN']);

export function toPaymentOutcome(error: unknown): PaymentOutcome | null {
  if (error === null || error === undefined) return null;

  if (!(error instanceof ApiError)) {
    return {
      failure: 'UNKNOWN',
      message: 'Something went wrong. Please try again.',
      isRetryable: true,
    };
  }

  if (error.isConnectivityError) {
    return { failure: 'CONNECTION', message: error.message, isRetryable: true };
  }

  const failure = BY_CODE[error.code] ?? 'UNKNOWN';

  return {
    failure,
    message: error.message,
    isRetryable: RETRYABLE.has(failure),
  };
}

/**
 * What the customer should be told about a payment, in their terms.
 *
 * Driven by the server's status rather than by anything the app observed. A
 * customer who closed the checkout page without paying and one whose card was
 * declined look identical from here, and only the provider knows the difference.
 */
export type CheckoutStage = 'IDLE' | 'STARTING' | 'AWAITING_PAYMENT' | 'CHECKING' | 'PAID' | 'FAILED';

export function stageLabel(stage: CheckoutStage): string {
  switch (stage) {
    case 'STARTING':
      return 'Setting up your payment';
    case 'AWAITING_PAYMENT':
      return 'Finish paying in your browser, then come back';
    case 'CHECKING':
      return 'Checking with your bank';
    case 'PAID':
      return 'Paid';
    case 'FAILED':
      return 'That payment did not go through';
    default:
      return '';
  }
}
