#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  king_phisher/client/windows/plugin_manager.py
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following disclaimer
#    in the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of the project nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import sys
import os
import traceback

from collections import namedtuple

from king_phisher import utilities
from king_phisher.client import application
from king_phisher.client import gui_utilities
from king_phisher.client.widget import managers
from king_phisher.client.plugins import ClientCatalogManager
from gi.repository import Gdk
from gi.repository import Gtk

__all__ = ('PluginManagerWindow',)

class PluginManagerWindow(gui_utilities.GladeGObject):
	"""
	The window which allows the user to selectively enable and disable plugins
	for the client application. This also handles configuration changes, so the
	enabled plugins will persist across application runs.
	"""
	dependencies = gui_utilities.GladeDependencies(
		children=(
			'expander_plugin_info',
			'grid_plugin_info',
			'label_plugin_info_authors',
			'label_plugin_info_for_compatible',
			'label_plugin_info_compatible',
			'label_plugin_info_description',
			'label_plugin_info_homepage',
			'label_plugin_info_title',
			'label_plugin_info_version',
			'paned_plugins',
			'scrolledwindow_plugins',
			'stack_plugin_info',
			'treeview_plugins',
			'textview_plugin_info',
			'viewport_plugin_info',
			'statusbar'
		)
	)
	top_gobject = 'window'

	def __init__(self, *args, **kwargs):
		super(PluginManagerWindow, self).__init__(*args, **kwargs)
		treeview = self.gobjects['treeview_plugins']
		self.status_bar = self.gobjects['statusbar']
		self._module_errors = {}
		tvm = managers.TreeViewManager(
			treeview,
			cb_refresh=self._load_plugins
		)
		toggle_renderer_enable = Gtk.CellRendererToggle()
		toggle_renderer_enable.connect('toggled', self.signal_renderer_toggled_enable)
		toggle_renderer_install = Gtk.CellRendererToggle()
		toggle_renderer_install.connect('toggled', self.signal_renderer_toggled_install)
		tvm.set_column_titles(
			['Installed', 'Enabled', 'Title', 'Compatible', 'Version'],
			column_offset=1,
			renderers=[
				toggle_renderer_install,
				toggle_renderer_enable,
				Gtk.CellRendererText(),
				Gtk.CellRendererText(),
				Gtk.CellRendererText()
			]
		)
		tvm.column_views['Enabled'].set_cell_data_func(toggle_renderer_enable, self._toggle_cell_data_func)
		tvm.column_views['Enabled'].add_attribute(toggle_renderer_enable, 'visible', 6)
		tvm.column_views['Enabled'].add_attribute(toggle_renderer_enable, 'sensitive', 7)
		tvm.column_views['Installed'].add_attribute(toggle_renderer_install, 'visible', 7)
		tvm.column_views['Installed'].add_attribute(toggle_renderer_install, 'sensitive', 8)
		self._named_model = namedtuple(
			'model_row',
			[
				'id',
				'installed',
				'enabled',
				'title',
				'compatibility',
				'version',
				'visible_enabled',
				'visible_installed',
				'installed_sensitive',
				'type'
			]
		)
		self._model = Gtk.TreeStore(str, bool, bool, str, str, str, bool, bool, bool, str)
		self._model.set_sort_column_id(1, Gtk.SortType.DESCENDING)
		treeview.set_model(self._model)
		self.plugin_path = os.path.join(application.USER_DATA_PATH, 'plugins')
		if 'catalogs' not in self.config:
			self.config['catalogs'] = ['https://raw.githubusercontent.com/securestate/king-phisher-plugins/dev/catalog.json']
		self.catalog_list = self.config['catalogs']
		self.load_thread = utilities.Thread(target=self._load_catalogs)
		self.load_thread.start()
		self.popup_menu = tvm.get_popup_menu()
		self.popup_menu.append(Gtk.SeparatorMenuItem())
		menu_item = Gtk.MenuItem.new_with_label('Reload')
		menu_item.connect('activate', self.signal_popup_menu_activate_reload)
		self.popup_menu.append(menu_item)
		menu_item_reload_all = Gtk.MenuItem.new_with_label('Reload All')
		menu_item_reload_all.connect('activate', self.signal_popup_menu_activate_reload_all)
		self.popup_menu.append(menu_item_reload_all)
		self.popup_menu.show_all()
		self._update_status_bar('Loading: ')
		self.window.show()

		selection = treeview.get_selection()
		selection.unselect_all()
		paned = self.gobjects['paned_plugins']
		self._paned_offset = paned.get_allocation().height - paned.get_position()

	def _treeview_unselect(self):
		treeview = self.gobjects['treeview_plugins']
		treeview.get_selection().unselect_all()
		self._update_status_bar('Finished Loading Plugin Store', idle=True)

	def signal_window_show(self, _):
		pass

	def _load_catalogs(self):
		self._update_status_bar('Loading: Downloading Catalogs', idle=True)
		self.catalog_plugins = ClientCatalogManager()
		for catalog in self.catalog_list:
			self.logger.debug("downloading catalog {}".format(catalog))
			self._update_status_bar("Loading: Downloading Catalog: {}".format(catalog))
			self.catalog_plugins.add_catalog_url(catalog)
		self._load_plugins()

	def __update_status_bar(self, string_to_set):
		self.status_bar.pop(0)
		self.status_bar.push(0, string_to_set)

	def _update_status_bar(self, string_to_set, idle=False):
		if idle:
			gui_utilities.glib_idle_add_once(self.__update_status_bar, string_to_set)
		else:
			self.__update_status_bar(string_to_set)

	def _model_item(self, model_path, item):
		named_row = self._named_model(*self._model[model_path])
		return getattr(named_row, item)

	def _set_model_item(self, model_path, item, item_value):
		self._model[model_path][self._named_model._fields.index(item)] = item_value

	def _on_plugin_load_error(self, name, error):
		self._module_errors[name] = (error, traceback.format_exception(*sys.exc_info(), limit=5))

	def _toggle_cell_data_func(self, column, cell, model, tree_iter, _):
		if model.get_value(tree_iter, 0) in self._module_errors:
			cell.set_property('inconsistent', True)
		else:
			cell.set_property('inconsistent', False)

	def _store_append(self, store, parent, model):
		return store.append(parent, model)

	def _load_plugins(self):
		"""
		Load the plugins which are available into the treeview to make them
		visible to the user.
		"""
		self.logger.debug('loading plugins')
		self._update_status_bar('Loading.... Plugins....', idle=True)
		store = self._model
		store.clear()
		pm = self.application.plugin_manager
		self._module_errors = {}
		pm.load_all(on_error=self._on_plugin_load_error)
		model = ('local', None, True, '[Locally Installed]', None, None, False, False, False, 'Catalog')
		catalog = gui_utilities.glib_idle_add_wait(self._store_append, store, None, model)
		for name, plugin in pm.loaded_plugins.items():
			if name in self.config['plugins.installed']:
				continue
			model = (
				plugin.name,
				True,
				plugin.name in pm.enabled_plugins,
				plugin.title,
				'Yes' if plugin.is_compatible else 'No',
				plugin.version,
				True,
				True,
				False,
				'Plugin'
			)
			gui_utilities.glib_idle_add_once(self._store_append, store, catalog, model)

		for name in self._module_errors.keys():
			model = (name, True, False, "{0} (Load Failed)".format(name), 'unknown', True, True, False, 'Plugin')
			gui_utilities.glib_idle_add_once(self._store_append, store, catalog, model)

		self.logger.debug('loading catalog into plugin treeview')
		if self.catalog_plugins.catalog_ids():
			for catalogs in self.catalog_plugins.catalog_ids():
				model = (catalogs, None, True, catalogs, None, None, False, False, False, 'Catalog')
				catalog = gui_utilities.glib_idle_add_wait(self._store_append, store, None, model)
				for repos in self.catalog_plugins.get_repositories(catalogs):
					model = (repos.id, None, True, repos.title, None, None, False, False, False, 'Repository')
					repo_line = gui_utilities.glib_idle_add_wait(self._store_append, store, catalog, model)
					plugin_collections = self.catalog_plugins.get_collection(catalogs, repos.id)
					self._add_plugins_to_tree(catalogs, repos, store, repo_line, plugin_collections)
		else:
			if not self.config['plugins.installed']:
				return
			for catalog_id in self.catalog_plugins.get_cache_catalog_ids():
				model = (catalog_id, None, True, "{} (offline)".format(catalog_id), None, None, False, False, False, 'Catalog (offline)')
				catalog_line = gui_utilities.glib_idle_add_wait(self._store_append, store, None, model)
				for repo in self.catalog_plugins.get_cache_repositories(catalog_id):
					model = (repo.id, None, True, "{} (offline)".format(repo.title), None, None, False, False, False, 'Repository (offline)')
					repo_line = gui_utilities.glib_idle_add_wait(self._store_append, store, catalog_line, model)
					self._add_plugins_offline(catalog_id, repo.id, store, repo_line)

		gui_utilities.glib_idle_add_once(self._treeview_unselect)

	def _add_plugins_to_tree(self, catalog, repo, store, parent, plugin_list):
		client_plugins = list(plugin_list)
		for plugins in client_plugins:
			installed = False
			enabled = False
			if plugin_list[plugins]['name'] in self.config['plugins.installed']:
				if repo.id == self.config['plugins.installed'][plugin_list[plugins]['name']][1]:
					installed = True
					enabled = True if plugin_list[plugins]['name'] in self.config['plugins.enabled'] else False
			model = (
				plugins,
				installed,
				enabled,
				plugin_list[plugins]['title'],
				'Yes' if self.catalog_plugins.is_compatible(catalog, repo.id, plugins) else 'No',
				self._get_version_or_upgrade(plugin_list[plugins]['name'], plugin_list[plugins]['version']),
				True,
				True,
				True,
				'Plugin'
			)
			gui_utilities.glib_idle_add_once(self._store_append, store, parent, model)

	def _add_plugins_offline(self, catalog_id, repo_id, store, parent):
		for plugin in self.config['plugins.installed']:
			if self.config['plugins.installed'][plugin][0] != catalog_id:
				continue
			if self.config['plugins.installed'][plugin][1] != repo_id:
				continue
			model = (
				plugin,
				True,
				True if plugin in self.config['plugins.enabled'] else False,
				self.application.plugin_manager[plugin].title,
				'Yes' if self.application.plugin_manager[plugin].is_compatible else 'No',
				self.application.plugin_manager[plugin].version,
				True,
				True,
				False,
				'Plugin'
			)
			gui_utilities.glib_idle_add_once(self._store_append, store, parent, model)

	def _get_version_or_upgrade(self, plugin_name, plugin_version):
		if plugin_name not in self.application.plugin_manager:
			return plugin_version
		if self.application.plugin_manager[plugin_name].version < plugin_version:
			return "Upgrade available"
		return self.application.plugin_manager[plugin_name].version

	def signal_popup_menu_activate_reload_all(self, _):
		self.load_thread = utilities.Thread(target=self._load_plugins)
		self.load_thread.start()

	def signal_destory(self, _):
		if self.catalog_plugins:
			self.catalog_plugins.save_catalog_cache()

	def signal_treeview_row_activated(self, treeview, path, column):
		self._set_plugin_info(self._model[path])

	def signal_label_activate_link(self, _, uri):
		utilities.open_uri(uri)

	def signal_eventbox_button_press(self, widget, event):
		if not (event.type == Gdk.EventType.BUTTON_PRESS and event.button == Gdk.BUTTON_PRIMARY):
			return
		if not self._last_plugin_selected:
			return
		named_plugin = self._named_model(*self._last_plugin_selected)
		plugin_id = named_plugin.id
		if plugin_id is None:
			return
		if plugin_id in self.application.plugin_manager:
			klass = self.application.plugin_manager[plugin_id]
			compatibility_details = list(klass.compatibility)
		else:
			repo_model, catalog_model = self._get_plugin_model_parents(self._last_plugin_selected)
			compatibility_details = list(self.catalog_plugins.compatibility(catalog_model.id, repo_model.id, named_plugin.id))

		popover = Gtk.Popover()
		popover.set_relative_to(self.gobjects['label_plugin_info_for_compatible'])
		grid = Gtk.Grid()
		popover.add(grid)
		grid.insert_column(0)
		grid.insert_column(0)
		grid.insert_column(0)
		grid.set_column_spacing(3)

		compatibility_details.insert(0, ('Type', 'Value', 'Met'))
		row = 0
		for row, req in enumerate(compatibility_details):
			grid.insert_row(row)
			label = Gtk.Label(req[0])
			label.set_property('halign', Gtk.Align.START)
			grid.attach(label, 0, row, 1, 1)
			label = Gtk.Label(req[1])
			label.set_property('halign', Gtk.Align.START)
			grid.attach(label, 1, row, 1, 1)
			label = Gtk.Label(('Yes' if req[2] else 'No') if row else req[2])
			label.set_property('halign', Gtk.Align.END)
			grid.attach(label, 2, row, 1, 1)
		if not row:
			popover.destroy()
			return
		popover.show_all()

	def signal_expander_activate(self, expander):
		paned = self.gobjects['paned_plugins']
		if expander.get_property('expanded'):  # collapsing
			paned.set_position(paned.get_allocation().height + self._paned_offset)

	def signal_paned_button_press_event(self, paned, event):
		return not self.gobjects['expander_plugin_info'].get_property('expanded')

	def signal_popup_menu_activate_reload(self, _):
		treeview = self.gobjects['treeview_plugins']
		pm = self.application.plugin_manager
		selected_plugin = None
		selection = treeview.get_selection()
		if selection.count_selected_rows():
			(model, tree_paths) = selection.get_selected_rows()
			selected_plugin = model[tree_paths[0]][0]

		for tree_iter in gui_utilities.gtk_treeview_selection_iterate(treeview):
			if self._model_item(tree_iter, 'type') != 'Plugin':
				continue
			plugin_id = self._model_item(tree_iter, 'id')
			enabled = plugin_id in pm.enabled_plugins
			pm.unload(plugin_id)
			try:
				klass = pm.load(plugin_id, reload_module=True)
			except Exception as error:
				self._on_plugin_load_error(plugin_id, error)
				if plugin_id == selected_plugin:
					self._set_plugin_info(plugin_id)
				self._set_model_item(tree_iter, 'title', "{0} (Reload Failed)".format(plugin_id))
				continue
			if plugin_id in self._module_errors:
				del self._module_errors[plugin_id]
			self._set_model_item(tree_iter, 'title', klass.title)
			if plugin_id == selected_plugin:
				self._set_plugin_info(plugin_id)
			if enabled:
				pm.enable(plugin_id)

	def signal_renderer_toggled_enable(self, _, path):
		pm = self.application.plugin_manager
		if self._model_item(path, 'type') != 'Plugin':
			return
		if self._model_item(path, 'id') not in pm.loaded_plugins:
			return
		if self._model[path].parent:
			installed_plugin_info = self.config['plugins.installed'][self._model_item(path, 'id')]
			repo_model, catalog_model = self._get_plugin_model_parents(self._model[path])
			if repo_model.id != installed_plugin_info[1] or catalog_model.id != installed_plugin_info[0]:
				return
		if self._model_item(path, 'id') in self._module_errors:
			gui_utilities.show_dialog_error('Can Not Enable Plugin', self.window, 'Can not enable a plugin which failed to load.')
			return
		if self._model_item(path, 'enabled'):
			self._disable_plugin(path)
		else:
			if not pm.loaded_plugins[self._model_item(path, 'id')].is_compatible:
				gui_utilities.show_dialog_error('Incompatible Plugin', self.window, 'This plugin is not compatible.')
				return
			if not pm.enable(self._model_item(path, 'id')):
				return
			self._set_model_item(path, 'enabled', True)
			self.config['plugins.enabled'].append(self._model_item(path, 'id'))

	def signal_renderer_toggled_install(self, _, path):
		repo_model, catalog_model = self._get_plugin_model_parents(self._model[path])
		plugin_collection = self.catalog_plugins.get_collection(catalog_model.id, repo_model.id)
		if self._model_item(path, 'installed'):
			if self._model_item(path, 'enabled'):
				response = gui_utilities.show_dialog_yes_no(
					'Plugin is enabled',
					self.window,
					"This will disable the plugin, do you wish to continue?"
				)
				if not response:
					return
				self._disable_plugin(path)
			self._uninstall_plugin(plugin_collection, path)
			self.logger.info("uninstalled plugin {}".format(self._model_item(path, 'id')))
		else:
			if self._model_item(path, 'id') in self.config['plugins.installed']:
				installed_plugin_info = self.config['plugins.installed'][self._model_item(path, 'id')]
				if installed_plugin_info != [catalog_model.id, repo_model.id]:
					window_question = "A plugin with this name is already installed from Catalog: {} Repo: {}\nDo you want to replace it with this one?"
					response = gui_utilities.show_dialog_yes_no(
						'Plugin installed from another source',
						self.window,
						window_question.format(installed_plugin_info[0], installed_plugin_info[1])
					)
					if not response:
						return
					if not self._remove_matching_plugin(path, installed_plugin_info):
						self.logger.warning('failed to uninstall plugin {}'.format(self._model_item(path, 'id')))
						return
			self.catalog_plugins.install_plugin(
				catalog_model.id,
				repo_model.id,
				self._model_item(path, 'id'),
				self.plugin_path
			)
			self.config['plugins.installed'][self._model_item(path, 'id')] = [catalog_model.id, repo_model.id]
			self._set_model_item(path, 'installed', True)
			self._set_model_item(
				path,
				'version',
				self.catalog_plugins.get_collection(catalog_model.id, repo_model.id)[self._model_item(path, 'id')]['version']
			)
			self.logger.info("installed plugin {} from catalog:{}, repository:{}".format(self._model_item(path, 'id'), catalog_model.id, repo_model.id))
		self.application.plugin_manager.load_all(on_error=self._on_plugin_load_error)

	def _disable_plugin(self, path, model_path=True):
		if not model_path:
			named_plugin = self._named_model(*path)
			self.application.plugin_manager.disable(named_plugin.id)
			self.config['plugins.enabled'].remove(named_plugin.id)
			path[self._named_model._fields.index('enabled')] = False
		else:
			plugin_id = self._model_item(path, 'id')
			self.application.plugin_manager.disable(plugin_id)
			self.config['plugins.enabled'].remove(plugin_id)
			self._set_model_item(path, 'enabled', False)

	def _remove_matching_plugin(self, path, installed_plugin_info):
		plugin_id = self._model_item(path, 'id')
		for catalog_model in self._model:
			if self._named_model(*catalog_model).id != installed_plugin_info[0]:
				continue
			for repo_model in catalog_model.iterchildren():
				if self._named_model(*repo_model).id != installed_plugin_info[1]:
					continue
				for plugin_model in repo_model.iterchildren():
					named_model = self._named_model(*plugin_model)
					if named_model.id != plugin_id:
						continue
					if named_model.enabled:
						self._disable_plugin(plugin_model, model_path=False)
					self._uninstall_plugin(
						self.catalog_plugins.get_collection(
							installed_plugin_info[0],
							installed_plugin_info[1]
						),
						plugin_model,
						is_path=False
					)
					return True

	def _get_plugin_model_parents(self, plugin_model):
		return self._named_model(*plugin_model.parent), self._named_model(*plugin_model.parent.parent)

	def _uninstall_plugin(self, plugin_collection, path, is_path=True):
		if is_path:
			plugin_id = self._model_item(path, 'id')
		else:
			plugin_id = self._named_model(*path).id
		for files in plugin_collection[plugin_id]['files']:
			file_name = files[0]
			if os.path.isfile(os.path.join(self.plugin_path, file_name)):
				os.remove(os.path.join(self.plugin_path, file_name))
			self.application.plugin_manager.unload(plugin_id)
		del self.config['plugins.installed'][plugin_id]
		if is_path:
			self._set_model_item(path, 'installed', False)
		else:
			path[self._named_model._fields.index('installed')] = False

	def _set_plugin_info(self, model_instance):
		named_model = self._named_model(*model_instance)
		stack = self.gobjects['stack_plugin_info']
		textview = self.gobjects['textview_plugin_info']
		buf = textview.get_buffer()
		buf.delete(buf.get_start_iter(), buf.get_end_iter())
		model_id = named_model.id
		if named_model.type != 'Plugin':
			stack.set_visible_child(textview)
			self._set_non_plugin_info(model_instance)
			return
		if model_id in self._module_errors:
			stack.set_visible_child(textview)
			self._set_plugin_info_error(model_id)
		else:
			stack.set_visible_child(self.gobjects['grid_plugin_info'])
			self._set_plugin_info_details(model_instance)

	def _set_non_plugin_info(self, model_instance):
		named_model = self._named_model(*model_instance)
		if 'offline' in named_model.type or named_model.id == 'local':
			self._set_non_plugin_offline_info(model_instance)
			return
		textview = self.gobjects['textview_plugin_info']
		buf = textview.get_buffer()
		text = ''
		if named_model.type == 'Catalog':
			instance_information = self.catalog_plugins.catalogs[named_model.id]
		else:
			instance_information = self.catalog_plugins.get_repository(self._named_model(*model_instance.parent).id, named_model.id)

		text += "{0}\n".format(named_model.type)
		text += "Title: {0}\n".format(getattr(instance_information, 'title', 'None'))
		text += "Id: {0}\n".format(getattr(instance_information, 'id', 'None'))
		text += "Description: {}\n".format(getattr(instance_information, 'description', 'None'))
		if hasattr(instance_information, 'maintainers'):
			text += 'Maintainer: ' + '\nMaintainer: '.join(getattr(instance_information, 'maintainers', ['None'])) + '\n'

		buf.insert(buf.get_end_iter(), "{0}\n".format(text), -1)

	def _set_non_plugin_offline_info(self, model_instance):
		named_model = self._named_model(*model_instance)
		textview = self.gobjects['textview_plugin_info']
		buf = textview.get_buffer()
		text = '{0}\n'.format(named_model.type.split()[0])
		text += "Title: {0}".format(named_model.title)
		buf.insert(buf.get_end_iter(), "{0}\n".format(text), -1)

	def _set_plugin_info_details(self, plugin_model):
		named_model = self._named_model(*plugin_model)
		model_id = named_model.id
		pm = self.application.plugin_manager
		self._last_plugin_selected = plugin_model
		if model_id in pm.loaded_plugins:
			klass = pm.loaded_plugins[model_id]
			self.gobjects['label_plugin_info_title'].set_text(klass.title)
			self.gobjects['label_plugin_info_compatible'].set_text('Yes' if klass.is_compatible else 'No')
			self.gobjects['label_plugin_info_version'].set_text(klass.version)
			self.gobjects['label_plugin_info_authors'].set_text('\n'.join(klass.authors))
			label_homepage = self.gobjects['label_plugin_info_homepage']
			if klass.homepage is None:
				label_homepage.set_property('visible', False)
			else:
				label_homepage.set_markup("<a href=\"{0}\">Homepage</a>".format(klass.homepage))
				label_homepage.set_property('tooltip-text', klass.homepage)
				label_homepage.set_property('visible', True)
			self.gobjects['label_plugin_info_description'].set_text(klass.description)
		else:
			repo_model, catalog_model = self._get_plugin_model_parents(plugin_model)
			for repo in self.catalog_plugins.get_repositories(catalog_model.id):
				if repo.id != repo_model.id:
					continue
				plugin = repo.collections['plugins/client'][named_model.id]
				self.gobjects['label_plugin_info_title'].set_text(plugin['title'])
				self.gobjects['label_plugin_info_compatible'].set_text(
					'Yes' if self.catalog_plugins.is_compatible(catalog_model.id, repo_model.id, named_model.id) else 'No'
				)
				self.gobjects['label_plugin_info_version'].set_text(plugin['version'])
				self.gobjects['label_plugin_info_authors'].set_text('\n'.join(plugin['authors']))
				label_homepage = self.gobjects['label_plugin_info_homepage']
				if plugin['homepage'] is None:
					label_homepage.set_property('visible', False)
				else:
					label_homepage.set_markup("<a href=\"{0}\">Homepage</a>".format(plugin['homepage']))
					label_homepage.set_property('tooltip-text', plugin['homepage'])
					label_homepage.set_property('visible', True)
				self.gobjects['label_plugin_info_description'].set_text(plugin['description'])

	def _set_plugin_info_error(self, model_instance):
		id_ = self._named_model(*model_instance).id
		textview = self.gobjects['textview_plugin_info']
		buf = textview.get_buffer()
		exc, formatted_exc = self._module_errors[id_]
		buf.insert(buf.get_end_iter(), "{0!r}\n\n".format(exc), -1)
		buf.insert(buf.get_end_iter(), ''.join(formatted_exc), -1)
