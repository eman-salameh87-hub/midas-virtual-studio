import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

export interface StudioSelectOption {
  value: string;
  label: string;
}

export interface StudioSelectGroup {
  label: string;
  options: readonly StudioSelectOption[];
}

export function StudioSelect({
  id,
  name,
  value,
  disabled = false,
  options = [],
  groups = [],
  onChange,
  "aria-label": ariaLabel,
}: {
  id?: string;
  name?: string;
  value: string;
  disabled?: boolean;
  options?: readonly StudioSelectOption[];
  groups?: readonly StudioSelectGroup[];
  onChange: (value: string) => void;
  "aria-label"?: string;
}) {
  const generatedId = useId();
  const listboxId = `${generatedId}-listbox`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef("");
  const searchTimer = useRef<number>(0);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuBox, setMenuBox] = useState({ top: 0, left: 0, width: 0, maxHeight: 280 });

  const flat = useMemo(() => {
    const next: StudioSelectOption[] = [...options];
    for (const group of groups) next.push(...group.options);
    return next;
  }, [groups, options]);

  const selectedLabel = flat.find((option) => option.value === value)?.label ?? "";
  const selectedIndex = Math.max(
    0,
    flat.findIndex((option) => option.value === value),
  );

  const placeMenu = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom - 8;
    const spaceAbove = rect.top - 8;
    const maxHeight = Math.min(280, Math.max(spaceBelow, spaceAbove, 120));
    const openUp = spaceBelow < Math.min(220, maxHeight) && spaceAbove > spaceBelow;
    setMenuBox({
      top: openUp ? Math.max(8, rect.top - maxHeight - 6) : rect.bottom + 6,
      left: rect.left,
      width: Math.max(rect.width, 180),
      maxHeight,
    });
  }, []);

  const close = useCallback(() => {
    setOpen(false);
  }, []);

  const openMenu = useCallback(() => {
    if (disabled) return;
    setActiveIndex(selectedIndex);
    setOpen(true);
  }, [disabled, selectedIndex]);

  useEffect(() => {
    if (!open) return;
    placeMenu();
    const onScroll = () => placeMenu();
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      close();
    };
    window.addEventListener("resize", placeMenu);
    window.addEventListener("scroll", onScroll, true);
    document.addEventListener("mousedown", onPointer);
    return () => {
      window.removeEventListener("resize", placeMenu);
      window.removeEventListener("scroll", onScroll, true);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [close, open, placeMenu]);

  useEffect(() => {
    if (!open) return;
    const option = menuRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
    option?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open]);

  function commit(next: string) {
    onChange(next);
    close();
    triggerRef.current?.focus();
  }

  function moveActive(delta: number) {
    if (flat.length === 0) return;
    setActiveIndex((current) => (current + delta + flat.length) % flat.length);
  }

  function search(letter: string) {
    window.clearTimeout(searchTimer.current);
    searchRef.current += letter.toLowerCase();
    searchTimer.current = window.setTimeout(() => {
      searchRef.current = "";
    }, 500);
    const match = flat.findIndex((option) => option.label.toLowerCase().startsWith(searchRef.current));
    if (match >= 0) setActiveIndex(match);
  }

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      moveActive(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Home" && open) {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }
    if (event.key === "End" && open) {
      event.preventDefault();
      setActiveIndex(Math.max(0, flat.length - 1));
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (!open) {
        openMenu();
        return;
      }
      const option = flat[activeIndex];
      if (option) commit(option.value);
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      close();
      return;
    }
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (!open) openMenu();
      search(event.key);
    }
  }

  const activeId = open && flat[activeIndex] ? `${generatedId}-option-${activeIndex}` : undefined;
  let optionIndex = -1;

  return (
    <div className="studio-select">
      <select
        id={id ? `${id}-native` : undefined}
        className="studio-select__native"
        name={name}
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={`flat-${option.value}`} value={option.value}>
            {option.label}
          </option>
        ))}
        {groups.map((group) => (
          <optgroup key={group.label} label={group.label}>
            {group.options.map((option) => (
              <option key={`${group.label}-${option.value}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className="studio-select__trigger"
        role="combobox"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-autocomplete="none"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={activeId}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={onTriggerKeyDown}
      >
        {selectedLabel}
      </button>
      {open
        ? createPortal(
            <div
              ref={menuRef}
              className="studio-select__menu"
              style={{
                top: menuBox.top,
                left: menuBox.left,
                width: menuBox.width,
                maxHeight: menuBox.maxHeight,
              }}
            >
              <div id={listboxId} role="listbox" aria-label={ariaLabel ?? selectedLabel} className="studio-select__list">
                {options.map((option) => {
                  optionIndex += 1;
                  const index = optionIndex;
                  return (
                    <SelectOptionRow
                      key={`flat-${option.value}`}
                      id={`${generatedId}-option-${index}`}
                      option={option}
                      index={index}
                      selected={option.value === value}
                      active={index === activeIndex}
                      onCommit={commit}
                      onActive={setActiveIndex}
                    />
                  );
                })}
                {groups.map((group) => (
                  <div key={group.label} className="studio-select__group" role="group" aria-label={group.label}>
                    <div className="studio-select__group-label">{group.label}</div>
                    {group.options.map((option) => {
                      optionIndex += 1;
                      const index = optionIndex;
                      return (
                        <SelectOptionRow
                          key={`${group.label}-${option.value}`}
                          id={`${generatedId}-option-${index}`}
                          option={option}
                          index={index}
                          selected={option.value === value}
                          active={index === activeIndex}
                          onCommit={commit}
                          onActive={setActiveIndex}
                        />
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

function SelectOptionRow({
  id,
  option,
  index,
  selected,
  active,
  onCommit,
  onActive,
}: {
  id: string;
  option: StudioSelectOption;
  index: number;
  selected: boolean;
  active: boolean;
  onCommit: (value: string) => void;
  onActive: (index: number) => void;
}) {
  return (
    <div
      id={id}
      role="option"
      data-index={index}
      aria-selected={selected}
      data-active={active ? "true" : "false"}
      className="studio-select__option"
      onMouseEnter={() => onActive(index)}
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => onCommit(option.value)}
    >
      {option.label}
    </div>
  );
}
