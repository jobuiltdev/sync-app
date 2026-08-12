import { useMutation, useQueryClient } from '@tanstack/react-query';

import {
  type AuthUser,
  type VerificationChallenge,
  authKeys,
  confirmEmailVerification,
  confirmPhoneVerification,
  requestEmailVerification,
  requestPhoneVerification,
  updatePhone,
} from '@/api/endpoints/auth';
import { useSessionStore } from '@/state/session';

/** Keeps the cached user and the session store in step after a change to the
 *  account, so every screen sees the new verification state at once. */
function useAdoptUser() {
  const setUser = useSessionStore((state) => state.setUser);
  const queryClient = useQueryClient();

  return (user: AuthUser) => {
    setUser(user);
    queryClient.setQueryData(authKeys.me, user);
  };
}

export function useUpdatePhone() {
  const adopt = useAdoptUser();

  return useMutation({
    mutationFn: (phone: string) => updatePhone(phone),
    onSuccess: adopt,
  });
}

export function useRequestPhoneVerification() {
  return useMutation<VerificationChallenge, unknown, void>({
    mutationFn: () => requestPhoneVerification(),
  });
}

export function useConfirmPhoneVerification() {
  const adopt = useAdoptUser();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ challengeId, code }: { challengeId: string; code: string }) =>
      confirmPhoneVerification(challengeId, code),
    onSuccess: (user) => {
      adopt(user);
      // Booking was refused while unverified, so anything cached under that
      // assumption is now stale.
      void queryClient.invalidateQueries({ queryKey: ['bookings'] });
    },
  });
}


export function useRequestEmailVerification() {
  return useMutation<VerificationChallenge, unknown, void>({
    mutationFn: () => requestEmailVerification(),
  });
}

export function useConfirmEmailVerification() {
  const adopt = useAdoptUser();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ challengeId, code }: { challengeId: string; code: string }) =>
      confirmEmailVerification(challengeId, code),
    onSuccess: (user) => {
      adopt(user);
      // Accepting a job was refused while unverified, so the inbox is stale.
      void queryClient.invalidateQueries({ queryKey: ['offers'] });
    },
  });
}
