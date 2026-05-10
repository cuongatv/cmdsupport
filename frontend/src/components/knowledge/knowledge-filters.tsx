"use client";

import { cn } from "@/lib/utils";

type KnowledgeType = {
  id: string;
  slug: string;
  name: string;
  color: string;
};

type Department = {
  id: string;
  name: string;
};

type Props = {
  types: KnowledgeType[];
  selectedType: string | null;
  onSelectType: (slug: string | null) => void;
  departments: Department[];
  selectedDepartment: string | null;
  onSelectDepartment: (id: string | null) => void;
};

export function KnowledgeFilters({
  types,
  selectedType,
  onSelectType,
  departments,
  selectedDepartment,
  onSelectDepartment,
}: Props) {
  return (
    <div className="flex flex-col gap-4">
      {/* Knowledge Type filter */}
      <div className="bg-card rounded-xl p-5 border border-border shadow-sahara">
        <h4 className="text-sm font-semibold text-foreground mb-3">
          Loại tri thức
        </h4>
        <div className="flex flex-col gap-1">
          <FilterItem
            label="Tất cả"
            active={selectedType === null}
            onClick={() => onSelectType(null)}
          />
          {types.map((type) => (
            <FilterItem
              key={type.slug}
              label={type.name}
              color={type.color}
              active={selectedType === type.slug}
              onClick={() =>
                onSelectType(selectedType === type.slug ? null : type.slug)
              }
            />
          ))}
        </div>
      </div>

      {/* Department filter */}
      {departments.length > 0 && (
        <div className="bg-card rounded-xl p-5 border border-border shadow-sahara">
          <h4 className="text-sm font-semibold text-foreground mb-3">
            Đơn vị
          </h4>
          <div className="flex flex-col gap-1">
            <FilterItem
              label="Tất cả đơn vị"
              active={selectedDepartment === null}
              onClick={() => onSelectDepartment(null)}
            />
            {departments.map((dept) => (
              <FilterItem
                key={dept.id}
                label={dept.name}
                icon="corporate_fare"
                active={selectedDepartment === dept.id}
                onClick={() =>
                  onSelectDepartment(selectedDepartment === dept.id ? null : dept.id)
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FilterItem({
  label,
  color,
  icon,
  active,
  onClick,
}: {
  label: string;
  color?: string;
  icon?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-left transition-colors w-full",
        active
          ? "bg-primary/10 text-primary font-medium"
          : "text-muted-foreground hover:bg-secondary/50"
      )}
    >
      {color ? (
        <span
          className="w-3 h-3 rounded-full shrink-0"
          style={{ backgroundColor: color }}
        />
      ) : (
        <span className="material-symbols-outlined text-sm">
          {icon || "select_all"}
        </span>
      )}
      {label}
    </button>
  );
}
