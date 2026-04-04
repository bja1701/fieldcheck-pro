-- FieldCheck Pro — Supabase Migration
-- Run this in your Supabase SQL Editor:
-- https://supabase.com/dashboard/project/YOUR_PROJECT/sql

-- ─── STORAGE BUCKET ────────────────────────────────────────────────────────
INSERT INTO storage.buckets (id, name, public)
VALUES ('project-files', 'project-files', false)
ON CONFLICT (id) DO NOTHING;

-- ─── PROJECTS TABLE ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.projects (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        text NOT NULL,
    client      text,
    address     text,
    phase       text DEFAULT 'rough-in',
    notes       text,
    status      text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'processing', 'review', 'complete', 'error')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS projects_set_updated_at ON public.projects;
CREATE TRIGGER projects_set_updated_at
    BEFORE UPDATE ON public.projects
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ─── PROJECT DOCUMENTS TABLE ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.project_documents (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  uuid NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    doc_type    text NOT NULL
                  CHECK (doc_type IN ('spec_url', 'bid_spreadsheet', 'plans_pdf', 'cabinets_pdf')),
    file_path   text,   -- Supabase Storage object path (for file uploads)
    spec_url    text,   -- Only set for doc_type = 'spec_url'
    uploaded_at timestamptz NOT NULL DEFAULT now()
);

-- ─── ROW LEVEL SECURITY: PROJECTS ──────────────────────────────────────────
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_select_own_projects" ON public.projects;
CREATE POLICY "users_select_own_projects" ON public.projects
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "users_insert_own_projects" ON public.projects;
CREATE POLICY "users_insert_own_projects" ON public.projects
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "users_update_own_projects" ON public.projects;
CREATE POLICY "users_update_own_projects" ON public.projects
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "users_delete_own_projects" ON public.projects;
CREATE POLICY "users_delete_own_projects" ON public.projects
    FOR DELETE USING (auth.uid() = user_id);

-- ─── ROW LEVEL SECURITY: PROJECT DOCUMENTS ─────────────────────────────────
ALTER TABLE public.project_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_select_own_documents" ON public.project_documents;
CREATE POLICY "users_select_own_documents" ON public.project_documents
    FOR SELECT USING (
        project_id IN (
            SELECT id FROM public.projects WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "users_insert_own_documents" ON public.project_documents;
CREATE POLICY "users_insert_own_documents" ON public.project_documents
    FOR INSERT WITH CHECK (
        project_id IN (
            SELECT id FROM public.projects WHERE user_id = auth.uid()
        )
    );

-- ─── ROW LEVEL SECURITY: STORAGE ───────────────────────────────────────────
-- Users can upload to their own folder: {user_id}/{project_id}/filename
DROP POLICY IF EXISTS "users_upload_own_files" ON storage.objects;
CREATE POLICY "users_upload_own_files" ON storage.objects
    FOR INSERT WITH CHECK (
        bucket_id = 'project-files' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );

-- Users can read their own files
DROP POLICY IF EXISTS "users_read_own_files" ON storage.objects;
CREATE POLICY "users_read_own_files" ON storage.objects
    FOR SELECT USING (
        bucket_id = 'project-files' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );

-- Users can delete their own files
DROP POLICY IF EXISTS "users_delete_own_files" ON storage.objects;
CREATE POLICY "users_delete_own_files" ON storage.objects
    FOR DELETE USING (
        bucket_id = 'project-files' AND
        (storage.foldername(name))[1] = auth.uid()::text
    );
