import { useState, useEffect } from 'react'

function VerticalNav({ cogs, selectedCategory, onSelectCategory }) {
  const [categories, setCategories] = useState([])

  useEffect(() => {
    if (cogs.length > 0) {
      const uniqueCategories = [...new Set(cogs.map(cog => cog.category))]
      const categoriesWithCounts = uniqueCategories.map(cat => ({
        name: cat,
        count: cogs.filter(c => c.category === cat).length,
        icon: getCategoryIcon(cat)
      }))
      setCategories([
        { name: 'All', count: cogs.length, icon: '📋' },
        ...categoriesWithCounts
      ])
    }
  }, [cogs])

  const getCategoryIcon = (category) => {
    const iconMap = {
      'AI': '🤖',
      'Voice': '🎤',
      'Music': '🎶',
      'Entertainment': '🎬',
      'Fun': '🎉',
      'Management': '⚙️',
      'Utility': '🔧',
      'Moderation': '🔨',
      'Updates': '📢'
    }
    return iconMap[category] || '📦'
  }

  return (
    <div className="w-64 bg-dark-light min-h-screen p-4 border-r border-dark-lighter">
      <div className="mb-8">
        <h2 className="text-2xl font-bold bg-gradient-to-r from-primary to-gold bg-clip-text text-transparent">
          JackyBot
        </h2>
        <p className="text-sm text-gray-400 mt-1">Configuration Panel</p>
      </div>

      <nav className="space-y-2">
        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-2">
          Categories
        </div>
        {categories.map((category) => (
          <button
            key={category.name}
            onClick={() => onSelectCategory(category.name)}
            className={`
              nav-item w-full text-left
              ${selectedCategory === category.name ? 'active' : ''}
            `}
          >
            <span className="text-xl">{category.icon}</span>
            <span className="flex-1">{category.name}</span>
            <span className="text-sm text-gray-400 bg-dark-lighter px-2 py-0.5 rounded">
              {category.count}
            </span>
          </button>
        ))}
      </nav>
    </div>
  )
}

export default VerticalNav

