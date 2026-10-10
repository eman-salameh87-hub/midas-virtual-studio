import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { markReferenceReady, revokePreview } from "../lib/references";
import type {
  AdvancedDraft,
  BriefItem,
  ClientJobDraft,
  ItemDraft,
  ItemMetadata,
  JobDraft,
  PreferencesDraft,
  ReferencesDraft,
  ScopeDraft,
  SuggestionsDraft,
} from "../types/draft";
import { createEmptyBriefItem, createEmptyDraft } from "./emptyDraft";

type Updater<T> = (current: T) => T;

interface DraftContextValue {
  draft: ClientJobDraft;
  activeItemId: string;
  setActiveItemId: (id: string) => void;
  addItem: () => void;
  removeItem: (id: string) => void;
  setJob: (update: Updater<JobDraft>) => void;
  setItem: (update: Updater<ItemDraft>) => void;
  setReferences: (update: Updater<ReferencesDraft>) => void;
  updateItemReferences: (itemId: string, update: Updater<ReferencesDraft>) => void;
  settleUploads: () => void;
  setScope: (update: Updater<ScopeDraft>) => void;
  setItemMetadata: (update: Updater<ItemMetadata>) => void;
  setPreferences: (update: Updater<PreferencesDraft>) => void;
  setSuggestions: (update: Updater<SuggestionsDraft>) => void;
  setAdvanced: (update: Updater<AdvancedDraft>) => void;
  reset: () => void;
}

const DraftContext = createContext<DraftContextValue | null>(null);

function revokeItemPreviews(item: BriefItem) {
  for (const reference of item.references.items) revokePreview(reference);
}

export function DraftProvider({
  children,
  initialDraft,
}: {
  children: ReactNode;
  initialDraft?: ClientJobDraft;
}) {
  const [draft, setDraft] = useState(() => initialDraft ?? createEmptyDraft());
  const [activeItemId, setActiveItemId] = useState(() => draft.items[0]?.id ?? "");
  const draftRef = useRef(draft);
  const activeItemIdRef = useRef(activeItemId);
  draftRef.current = draft;
  activeItemIdRef.current = activeItemId;

  const updateActiveItem = useCallback((update: Updater<BriefItem>) => {
    setDraft((current) => ({
      ...current,
      items: current.items.map((item) => (item.id === activeItemIdRef.current ? update(item) : item)),
    }));
  }, []);

  const setJob = useCallback((update: Updater<JobDraft>) => {
    setDraft((current) => ({ ...current, job: update(current.job) }));
  }, []);

  const setItem = useCallback(
    (update: Updater<ItemDraft>) => {
      updateActiveItem((current) => ({ ...current, item: update(current.item) }));
    },
    [updateActiveItem],
  );

  const updateItemReferences = useCallback((itemId: string, update: Updater<ReferencesDraft>) => {
    setDraft((current) => ({
      ...current,
      items: current.items.map((item) =>
        item.id === itemId ? { ...item, references: update(item.references) } : item,
      ),
    }));
  }, []);

  const settleUploads = useCallback(() => {
    setDraft((current) => ({
      ...current,
      items: current.items.map((item) => ({
        ...item,
        references: {
          ...item.references,
          items: item.references.items.map((reference) =>
            reference.localStatus === "uploading" ? markReferenceReady(reference) : reference,
          ),
        },
      })),
    }));
  }, []);

  const setReferences = useCallback(
    (update: Updater<ReferencesDraft>) => {
      updateItemReferences(activeItemIdRef.current, update);
    },
    [updateItemReferences],
  );

  const setScope = useCallback(
    (update: Updater<ScopeDraft>) => {
      updateActiveItem((current) => ({ ...current, scope: update(current.scope) }));
    },
    [updateActiveItem],
  );

  const setItemMetadata = useCallback(
    (update: Updater<ItemMetadata>) => {
      updateActiveItem((current) => ({ ...current, metadata: update(current.metadata) }));
    },
    [updateActiveItem],
  );

  const setPreferences = useCallback((update: Updater<PreferencesDraft>) => {
    setDraft((current) => ({ ...current, preferences: update(current.preferences) }));
  }, []);

  const setSuggestions = useCallback((update: Updater<SuggestionsDraft>) => {
    setDraft((current) => ({ ...current, suggestions: update(current.suggestions) }));
  }, []);

  const setAdvanced = useCallback((update: Updater<AdvancedDraft>) => {
    setDraft((current) => ({ ...current, advanced: update(current.advanced) }));
  }, []);

  const addItem = useCallback(() => {
    const created = createEmptyBriefItem();
    setDraft((current) => ({ ...current, items: [...current.items, created] }));
    setActiveItemId(created.id);
  }, []);

  const removeItem = useCallback((id: string) => {
    const current = draftRef.current;
    if (current.items.length < 2) return;
    const removed = current.items.find((item) => item.id === id);
    if (removed) revokeItemPreviews(removed);
    const items = current.items.filter((item) => item.id !== id);
    setDraft({ ...current, items });
    if (activeItemIdRef.current === id) setActiveItemId(items[0]?.id ?? "");
  }, []);

  const reset = useCallback(() => {
    for (const item of draftRef.current.items) revokeItemPreviews(item);
    const next = createEmptyDraft();
    setDraft(next);
    setActiveItemId(next.items[0]?.id ?? "");
  }, []);

  const value = useMemo(
    () => ({
      draft,
      activeItemId,
      setActiveItemId,
      addItem,
      removeItem,
      setJob,
      setItem,
      setReferences,
      updateItemReferences,
      settleUploads,
      setScope,
      setItemMetadata,
      setPreferences,
      setSuggestions,
      setAdvanced,
      reset,
    }),
    [
      draft,
      activeItemId,
      addItem,
      removeItem,
      setJob,
      setItem,
      setReferences,
      updateItemReferences,
      settleUploads,
      setScope,
      setItemMetadata,
      setPreferences,
      setSuggestions,
      setAdvanced,
      reset,
    ],
  );

  return <DraftContext.Provider value={value}>{children}</DraftContext.Provider>;
}

function useDraftContext(): DraftContextValue {
  const value = useContext(DraftContext);
  if (!value) throw new Error("DraftProvider is missing.");
  return value;
}

function activeBriefItem(draft: ClientJobDraft, activeItemId: string): BriefItem {
  return draft.items.find((item) => item.id === activeItemId) ?? draft.items[0];
}

export function useClientJobDraft(): ClientJobDraft {
  return useDraftContext().draft;
}

export function useActiveItemId(): string {
  return useDraftContext().activeItemId;
}

export function useResetDraft(): () => void {
  return useDraftContext().reset;
}

export function useBatchItems() {
  const { draft, activeItemId, setActiveItemId, addItem, removeItem } = useDraftContext();
  return { items: draft.items, activeItemId, setActiveItemId, addItem, removeItem };
}

export function useJobDraft() {
  const { draft, setJob } = useDraftContext();
  return [draft.job, setJob] as const;
}

export function useItemDraft() {
  const { draft, activeItemId, setItem } = useDraftContext();
  return [activeBriefItem(draft, activeItemId).item, setItem] as const;
}

export function useReferencesDraft() {
  const { draft, activeItemId, setReferences, updateItemReferences, settleUploads } = useDraftContext();
  const item = activeBriefItem(draft, activeItemId);
  return [item.references, setReferences, item.id, updateItemReferences, settleUploads] as const;
}

export function useScopeDraft() {
  const { draft, activeItemId, setScope } = useDraftContext();
  return [activeBriefItem(draft, activeItemId).scope, setScope] as const;
}

export function useItemMetadata() {
  const { draft, activeItemId, setItemMetadata } = useDraftContext();
  return [activeBriefItem(draft, activeItemId).metadata, setItemMetadata] as const;
}

export function usePreferencesDraft() {
  const { draft, setPreferences } = useDraftContext();
  return [draft.preferences, setPreferences] as const;
}

export function useSuggestionsDraft() {
  const { draft, setSuggestions } = useDraftContext();
  return [draft.suggestions, setSuggestions] as const;
}

export function useAdvancedDraft() {
  const { draft, setAdvanced } = useDraftContext();
  return [draft.advanced, setAdvanced] as const;
}
