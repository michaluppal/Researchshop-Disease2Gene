import researchShopMark from '../../../resources/icon-source.svg'

interface BrandMarkProps {
  className?: string
  alt?: string
}

export default function BrandMark({
  className = 'h-6 w-6',
  alt = 'ResearchShop logo',
}: BrandMarkProps) {
  return (
    <img
      src={researchShopMark}
      alt={alt}
      className={className}
      draggable={false}
    />
  )
}
