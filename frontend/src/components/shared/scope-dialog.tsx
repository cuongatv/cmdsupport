"use client";

import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  employeeId: string;
};

/**
 * Scope dialog for managing personal access scopes.
 * Currently a placeholder — full implementation deferred to RBAC phase.
 */
export function ScopeDialog({ open, onOpenChange, label }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-lg flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">lock</span>
            Quyền truy cập cá nhân — {label}
          </DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <p className="text-sm text-muted-foreground">
            Quản lý phạm vi truy cập cá nhân sẽ có trong bản cập nhật tương lai.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
