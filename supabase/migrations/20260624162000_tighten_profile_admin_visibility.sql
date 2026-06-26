drop policy if exists "profiles admin scoped read" on public.profiles;

create policy "profiles admin scoped read"
on public.profiles for select
to authenticated
using (
  public.current_is_super_admin()
  or (
    public.current_is_admin()
    and org_id = (select org_id from public.current_profile())
    and super_admin = false
  )
  or id = auth.uid()
);
