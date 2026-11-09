-- Percha · esquema de Supabase (ejecutar una vez en el SQL Editor)

create table if not exists public.garments (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name           text not null check (char_length(name) between 1 and 60),
  category       text not null check (category in ('Vestidos','Poleras','Chaquetas','Pantalones','Calzado','Accesorios')),
  original_path  text not null,   -- foto tomada por el usuario
  cut_path       text not null,   -- PNG segmentado por la IA
  dominant_color text check (dominant_color ~ '^#[0-9a-fA-F]{6}$'),
  created_at     timestamptz not null default now()
);
create index if not exists garments_user_created_idx on public.garments (user_id, created_at);

alter table public.garments enable row level security;
create policy "garments_select_own" on public.garments for select to authenticated using (user_id = (select auth.uid()));
create policy "garments_insert_own" on public.garments for insert to authenticated with check (user_id = (select auth.uid()));
create policy "garments_update_own" on public.garments for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "garments_delete_own" on public.garments for delete to authenticated using (user_id = (select auth.uid()));

-- Bucket privado: <user_id>/<garment_id>/original.jpg y cut.png
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('garments', 'garments', false, 5242880, array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;

create policy "garments_files_select" on storage.objects for select to authenticated
  using (bucket_id = 'garments' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "garments_files_insert" on storage.objects for insert to authenticated
  with check (bucket_id = 'garments' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "garments_files_delete" on storage.objects for delete to authenticated
  using (bucket_id = 'garments' and (storage.foldername(name))[1] = (select auth.uid())::text);
