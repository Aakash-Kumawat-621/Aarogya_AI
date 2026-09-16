ALTER TABLE public.profiles
  ADD COLUMN age INTEGER,
  ADD COLUMN gender TEXT;

GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
GRANT ALL ON public.profiles TO service_role;