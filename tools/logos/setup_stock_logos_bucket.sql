-- Chạy 1 lần trong Supabase SQL Editor.
-- Bucket public để website đọc logo trực tiếp; upload vẫn dùng secret key ở tool local.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('stock-logos', 'stock-logos', true, 1048576, array['image/webp'])
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;
