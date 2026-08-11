import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type AuthSession,
  type LoginInput,
  type RegistrationInput,
  authKeys,
  fetchCurrentUser,
  login,
  register,
} from '@/api/endpoints/auth';
import { useSessionStore } from '@/state/session';

function useAdoptSession() {
  const signIn = useSessionStore((state) => state.signIn);
  const queryClient = useQueryClient();

  return async (session: AuthSession) => {
    await signIn(session);
    // Seed the cache from the response the server already gave us, so the first
    // authenticated screen renders without a second round trip.
    queryClient.setQueryData(authKeys.me, session.user);
  };
}

export function useRegister() {
  const adopt = useAdoptSession();

  return useMutation({
    mutationFn: (input: RegistrationInput) => register(input),
    onSuccess: adopt,
  });
}

export function useLogin() {
  const adopt = useAdoptSession();

  return useMutation({
    mutationFn: (input: LoginInput) => login(input),
    onSuccess: adopt,
  });
}

export function useSignOut() {
  const signOut = useSessionStore((state) => state.signOut);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => signOut(),
    onSuccess: () => {
      // Everything cached was fetched as the previous user.
      queryClient.clear();
    },
  });
}

export function useCurrentUser() {
  const status = useSessionStore((state) => state.status);
  const setUser = useSessionStore((state) => state.setUser);

  return useQuery({
    queryKey: authKeys.me,
    queryFn: async ({ signal }) => {
      const user = await fetchCurrentUser(signal);
      setUser(user);
      return user;
    },
    enabled: status === 'authenticated',
  });
}
