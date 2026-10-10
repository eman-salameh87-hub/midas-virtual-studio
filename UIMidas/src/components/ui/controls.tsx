import { useRef, type ReactNode } from "react";

export function ChoiceCard({
  name,
  value,
  label,
  description,
  checked,
  onChange,
  type = "radio",
  accent,
}: {
  name: string;
  value: string;
  label: string;
  description?: string;
  checked: boolean;
  onChange: () => void;
  type?: "radio" | "checkbox" | "toggle";
  accent?: "daylight" | "afternoon" | "evening";
}) {
  const id = `${name}-${value}`;
  const body = (
    <>
      {accent ? <span className="choice__tone" aria-hidden="true" /> : null}
      <span className="choice__title">{label}</span>
      <span className="choice__mark" aria-hidden="true" />
      {description ? <span className="choice__hint">{description}</span> : null}
    </>
  );

  if (type === "toggle") {
    return (
      <button
        type="button"
        className="choice"
        data-shape="circle"
        data-accent={accent}
        aria-pressed={checked}
        onClick={onChange}
      >
        {body}
      </button>
    );
  }

  return (
    <label className="choice" data-shape={type === "checkbox" ? "box" : "circle"} data-accent={accent}>
      <input id={id} className="choice__input" type={type} name={name} value={value} checked={checked} onChange={onChange} />
      <span className="choice__body">{body}</span>
    </label>
  );
}

export function OptionGroup({
  legend,
  hint,
  children,
}: {
  legend: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="option-group">
      <legend>{legend}</legend>
      {hint ? <p className="note">{hint}</p> : null}
      {children}
    </fieldset>
  );
}

export function ToggleChip({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className="chip" aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

export function SwatchButton({
  pressed,
  onClick,
  label,
  swatch,
}: {
  pressed: boolean;
  onClick: () => void;
  label: string;
  swatch: string;
}) {
  return (
    <button type="button" className="swatch" aria-pressed={pressed} onClick={onClick}>
      <span className="swatch__chip" style={{ background: swatch }} aria-hidden="true" />
      <span className="swatch__label">{label}</span>
    </button>
  );
}

export function SwitchRow({
  checked,
  onChange,
  title,
  hint,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  title: string;
  hint?: string;
}) {
  return (
    <button type="button" className="switch" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}>
      <span>
        <span className="switch__title">{title}</span>
        {hint ? <span className="switch__hint">{hint}</span> : null}
      </span>
      <span className="switch__track" aria-hidden="true">
        <span className="switch__thumb" />
      </span>
    </button>
  );
}

export function TextField({
  id,
  label,
  value,
  onChange,
  hint,
  placeholder,
  multiline = false,
  rows = 3,
  wide = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  placeholder?: string;
  multiline?: boolean;
  rows?: number;
  wide?: boolean;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const className = ["field", wide || multiline ? "field--wide" : ""].filter(Boolean).join(" ");
  return (
    <div className={className}>
      <label htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea
          id={id}
          rows={rows}
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          aria-describedby={hintId}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : (
        <input
          id={id}
          type="text"
          value={value}
          autoComplete="off"
          aria-describedby={hintId}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function NumberField({
  id,
  label,
  value,
  onChange,
  hint,
  narrow = false,
}: {
  id: string;
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  hint?: string;
  narrow?: boolean;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className={narrow ? "field field--narrow" : "field"}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={1}
        step={1}
        value={value ?? ""}
        aria-describedby={hintId}
        onChange={(event) => {
          const next = event.target.value;
          if (next === "") {
            onChange(null);
            return;
          }
          const parsed = Number(next);
          onChange(Number.isNaN(parsed) ? null : parsed);
        }}
      />
      {hint ? (
        <p id={hintId} className="field__hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FileButton({
  label,
  accept,
  multiple = true,
  onFiles,
}: {
  label: string;
  accept: string;
  multiple?: boolean;
  onFiles: (files: FileList) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className="btn btn--secondary" onClick={() => inputRef.current?.click()}>
        {label}
      </button>
      <input
        ref={inputRef}
        className="sr-only"
        tabIndex={-1}
        type="file"
        accept={accept}
        multiple={multiple}
        aria-hidden="true"
        onChange={(event) => {
          if (event.target.files && event.target.files.length > 0) onFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </>
  );
}
