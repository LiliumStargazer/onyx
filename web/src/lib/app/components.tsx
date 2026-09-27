"use client";

import Image from "next/image";
import { APP_NAME, DEFAULT_LOGO_SIZE_PX } from "@/lib/constants";
import { cn } from "@opal/utils";
import Truncated from "@/refresh-components/texts/Truncated";
import { SvgOnyxLogo, SvgOnyxLogoTyped } from "@opal/logos";
import { IconProps } from "@opal/types";

export interface LogoProps extends IconProps {
  // Craft uses the upstream mark for its own Onyx-branded surfaces.
  onyxBranded?: boolean;
}

export function Logo({ size, className, style, onyxBranded }: LogoProps) {
  const resolvedSize = size ?? DEFAULT_LOGO_SIZE_PX;

  if (onyxBranded) {
    return (
      <SvgOnyxLogo
        size={resolvedSize}
        className={cn("shrink-0", className)}
        style={style}
      />
    );
  }

  return (
    <Image
      alt={APP_NAME}
      src="/wiki-agent-rag.png"
      width={resolvedSize}
      height={resolvedSize}
      className={cn("shrink-0", className)}
      style={style}
    />
  );
}

export interface FoldableLogoProps extends LogoProps {
  folded?: boolean;
}

export function FoldableLogo({
  folded,
  size,
  className,
  onyxBranded,
}: FoldableLogoProps) {
  const resolvedSize = size ?? DEFAULT_LOGO_SIZE_PX;

  if (onyxBranded) {
    return folded ? (
      <Logo onyxBranded size={resolvedSize} className={className} />
    ) : (
      <SvgOnyxLogoTyped size={resolvedSize} className={className} />
    );
  }

  const logo = <Logo size={resolvedSize} className={className} />;
  return folded ? (
    logo
  ) : (
    <div className="flex min-w-0 gap-2 items-center">
      {logo}
      <Truncated headingH3>{APP_NAME}</Truncated>
    </div>
  );
}
